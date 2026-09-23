from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .catalyst import classify
from .config import load_config
from .db import SchemeIntelDB
from .exceptions import ConfigurationError, SourceAccessError, DataParseError, TelegramError
from .logger import get_logger
from .models import AnalysisReport, Article, now_utc
from .notifier import send_telegram, validate_telegram_config
from .reliability import SourceReliabilityTracker
from .signals import make_setup
from .sources import deduplicate_articles, fetch_rss, scan_page

logger = get_logger(__name__)

# Ingested price history is used for setups only while it is fresh.
INGESTED_MAX_AGE_HOURS = 26

# India Standard Time offset (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> datetime.date:
    """Return today's date in IST."""
    return datetime.now(IST).date()


def article_is_today(article: Article) -> bool:
    """Check if an article was published today (IST)."""
    if article.published_at is None:
        return False
    dt = article.published_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_ist = dt.astimezone(IST)
    return dt_ist.date() == today_ist()


class Pipeline:
    """
    Core pipeline that runs the full Scheme Intel workflow.

    When ``data/ingested.json`` (written by the ingestion layer) exists it is
    consumed as the shared data source:

      * ingested news + exchange announcements -> catalyst candidates
      * ingested OHLC price history -> swing setups (no live weather dependency)

    everything else behaves as before, so the pipeline still runs standalone.
    """

    def __init__(self, config_path: Optional[Path | str] = None, db_path: Optional[Path | str] = None):
        self.config_path = config_path
        self.config: dict | None = None
        self.root = Path(__file__).resolve().parents[2]
        self.db = SchemeIntelDB(db_path)
        self.reliability = SourceReliabilityTracker(db=self.db)

    def load_config(self) -> dict:
        """Load and validate watchlist configuration."""
        return load_config(self.config_path)

    # ------------------------------------------------------------------ ingestion

    def load_ingested(self, root: Optional[Path] = None) -> dict | None:
        """Load the ingestion snapshot from data/ingested.json."""
        path = (root or self.root) / "data" / "ingested.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            logger.info(f"Loaded ingested snapshot from {path}")
            return payload if isinstance(payload, dict) else None
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Could not parse ingested snapshot {path}: {exc}")
            return None

    @staticmethod
    def _parse_date(value: object) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None

    def ingested_articles(self, ingested: dict) -> list[Article]:
        """Turn ingested news + exchange announcements into catalyst candidates."""
        articles: list[Article] = []
        for news in ingested.get("news", []):
            articles.append(Article(
                title=str(news.get("title", "")),
                url=str(news.get("url", "")),
                source=str(news.get("source", "Media")),
                published_at=self._parse_date(news.get("published_at")),
                summary=str(news.get("summary", "")),
            ))
        for announcement in ingested.get("announcements", []):
            company = str(announcement.get("company", "")).strip()
            title = str(announcement.get("title", "")).strip()
            if company and company.lower() not in title.lower():
                title = f"{company}: {title}"
            articles.append(Article(
                title=title,
                url=str(announcement.get("url", "")),
                source=f"{announcement.get('exchange', '')} announcement",
                published_at=self._parse_date(announcement.get("date")),
                summary="",
            ))
        return articles

    def history_by_symbol(self, ingested: dict) -> dict[str, list[dict]]:
        """
        Map NSE ticker -> fresh OHLC history from the ingested price snapshots.

        Snapshots are only used for setups while newer than INGESTED_MAX_AGE_HOURS;
        older ones fall back to a live price fetch in ``make_setup``.
        """
        generated_at = self._parse_date(ingested.get("generated_at"))
        if generated_at is None or (now_utc() - generated_at) > timedelta(hours=INGESTED_MAX_AGE_HOURS):
            logger.info("Ingested price snapshot is stale; setups will fetch live prices")
            return {}

        history_map: dict[str, list[dict]] = {}
        for snapshot in ingested.get("prices", []):
            symbol = str(snapshot.get("symbol", ""))
            if not symbol:
                continue
            history = snapshot.get("history")
            if history:
                history_map[symbol.split(".")[0].upper()] = history
        logger.info(f"Mapped fresh ingested history for {len(history_map)} symbols")
        return history_map

    def dma200_by_symbol(self, ingested: dict) -> dict[str, float]:
        """Map NSE ticker -> current 200-day moving average from the ingested snapshots."""
        generated_at = self._parse_date(ingested.get("generated_at"))
        if generated_at is None or (now_utc() - generated_at) > timedelta(hours=INGESTED_MAX_AGE_HOURS):
            return {}
        out: dict[str, float] = {}
        for snapshot in ingested.get("prices", []):
            symbol = str(snapshot.get("symbol", ""))
            if not symbol:
                continue
            dma200 = snapshot.get("dma200")
            if dma200 is not None:
                out[symbol.split(".")[0].upper()] = float(dma200)
        return out

    # ----------------------------------------------------------------- sources

    def fetch_articles(self, config: dict, ingested: Optional[dict] = None) -> tuple[list, list]:
        """Fetch articles from configured sources and ingested news/announcements."""
        aliases = config["scheme"].get("aliases", []) + [
            alias for company in config.get("stocks", [])
            for alias in [company["name"], *company.get("aliases", [])]
        ]

        articles = []
        source_errors = []

        for source in config["scheme"].get("official_sources", []):
            name = source.get("name", "Unknown Source")
            url = source.get("url", "")
            source_type = source.get("type", "").lower()

            try:
                if source_type == "rss" or url.endswith((".xml", ".rss")):
                    fetched = fetch_rss(name, url)
                else:
                    fetched = scan_page(name, url, aliases)
                articles.extend(fetched)
                self.reliability.record_success(name)
                logger.debug(f"Fetched {len(fetched)} articles from {name}")
            except (SourceAccessError, DataParseError) as error:
                self.reliability.record_error(name)
                logger.warning(f"Source failure for '{name}': {error}")
                source_errors.append({"source": name, "error": str(error)[:180]})
            except Exception as error:
                self.reliability.record_error(name)
                logger.error(f"Unexpected error scanning '{name}': {error}")
                source_errors.append({"source": name, "error": str(error)[:180]})

        if ingested:
            ingested_articles = self.ingested_articles(ingested)
            articles.extend(ingested_articles)
            logger.info(f"Added {len(ingested_articles)} articles from the ingested snapshot")
            for error in ingested.get("source_errors", []):
                source_errors.append({
                    "source": f"ingestion::{error.get('source', 'unknown')}",
                    "error": str(error.get("error", ""))[:180],
                })

        deduped = deduplicate_articles(articles)

        # Filter to only today's articles (IST)
        today = today_ist()
        today_articles = [a for a in deduped if article_is_today(a)]
        logger.info(f"Total unique articles: {len(deduped)}, today's articles: {len(today_articles)}")

        return today_articles, source_errors

    # ---------------------------------------------------------------- catalysts

    def detect_catalysts(self, articles: list, config: dict) -> tuple[list, list]:
        """Detect catalysts, filter material ones, and score confidence."""
        catalysts = [item for article in articles if (item := classify(article, config["stocks"]))]
        min_score = config.get("settings", {}).get("minimum_catalyst_score", 60)
        material = [item for item in catalysts if item.score >= min_score]

        # Score confidence for material catalysts
        scored = self.reliability.score_catalysts(material, articles)

        logger.info(f"Classified {len(catalysts)} catalysts ({len(material)} material with score >= {min_score})")
        return material, catalysts, scored

    # ------------------------------------------------------------------- setups

    def generate_setups(self, material_catalysts: list, config: dict,
                        history_by_symbol: Optional[dict[str, list[dict]]] = None,
                        dma200_by_symbol: Optional[dict[str, float]] = None) -> list:
        """Generate swing setups for material catalysts."""
        history_by_symbol = history_by_symbol or {}
        dma200_by_symbol = dma200_by_symbol or {}
        setups = []
        for catalyst in material_catalysts:
            for company in config["stocks"]:
                if company["name"] in catalyst.companies and company.get("symbol"):
                    try:
                        symbol = company["symbol"]
                        history = history_by_symbol.get(symbol.split(".")[0].upper())
                        dma200 = dma200_by_symbol.get(symbol.split(".")[0].upper())
                        setup = make_setup(company["name"], symbol, catalyst.score, history=history, dma200=dma200)
                        if setup:
                            setups.append(setup.to_dict())
                            source = "ingested" if history else "live"
                            logger.info(f"Generated {setup.status} setup for {company['name']} ({symbol}) [{source}]")
                    except Exception as e:
                        logger.error(f"Failed to generate setup for {company['name']}: {e}")
        return setups

    # ------------------------------------------------------------------ output

    def save_report(self, report: dict, root: Path):
        """Save the analysis report to data/latest.json."""
        data_dir = root / "data"
        data_dir.mkdir(exist_ok=True)
        (data_dir / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.info(f"Saved latest report snapshot to {data_dir / 'latest.json'}")

    def send_alert(self, material_catalysts: list, setups: list, root: Path):
        """Optionally send a Telegram alert."""
        if not material_catalysts:
            return
        if validate_telegram_config():
            lines = ["GOBARdhan / CBG catalyst alert"]
            lines.extend(f"• [{c.score}] {c.article.title}\n{c.article.url}" for c in material_catalysts)
            if setups:
                lines.append("\nSetups require an entry trigger; this is research, not investment advice.")
                for s in setups:
                    extras = []
                    if s.get("volume_ratio") is not None:
                        extras.append(f"vol {s['volume_ratio']:.1f}x")
                    if s.get("macd_hist") is not None:
                        extras.append(f"MACD {s['macd_hist']:+.3f}")
                    if s.get("week_trend"):
                        extras.append(f"weekly {s['week_trend']}")
                    if s.get("dma200") is not None:
                        extras.append(f"200DMA {s['dma200']}")
                    suffix = f" — {', '.join(extras)}" if extras else ""
                    lines.append(
                        f"• {s['company']}: entry {s['entry']}, stop {s['stop']}, "
                        f"target {s['target']} ({s['status']}){suffix}"
                    )
            try:
                send_telegram("\n".join(lines))
                logger.info("Telegram notification sent successfully")
            except TelegramError as e:
                logger.error(f"Failed to send Telegram notification: {e}")
        else:
            logger.warning("Telegram send requested but credentials are not configured")

    # -------------------------------------------------------------------- main

    def run(self, send: bool = False) -> dict:
        """Execute the full pipeline, consuming the ingested snapshot when present."""
        logger.info("Starting scheme-intel scan run...")
        self.config = self.load_config()

        ingested = self.load_ingested(self.root)
        articles, source_errors = self.fetch_articles(self.config, ingested)
        material_catalysts, all_catalysts, scored_catalysts = self.detect_catalysts(articles, self.config)
        history_by_symbol = self.history_by_symbol(ingested) if ingested else {}
        dma200_by_symbol = self.dma200_by_symbol(ingested) if ingested else {}
        setups = self.generate_setups(material_catalysts, self.config, history_by_symbol, dma200_by_symbol)

        if ingested and "prices" in ingested:
            for p in ingested.get("prices", []):
                sym = p.get("symbol")
                hist = p.get("history")
                if sym and hist:
                    try:
                        self.db.save_historical_prices(sym, hist)
                    except Exception as e:
                        logger.debug(f"Failed to save historical prices for {sym}: {e}")

        generated_time = now_utc().isoformat()
        report_obj = AnalysisReport(
            generated_at=generated_time,
            catalysts=[
                {
                    "title": c.article.title,
                    "headline": getattr(c, "headline", c.article.title),
                    "url": c.article.url,
                    "score": c.score,
                    "category": c.category,
                    "catalyst_type": getattr(c, "catalyst_type", c.category),
                    "companies": c.companies,
                    "confidence": round(conf.confidence, 2),
                    "source": c.article.source,
                    "source_tier": getattr(c, "source_tier", 3),
                    "source_reliability": round(conf.source_reliability, 2),
                    "corroboration_count": conf.corroboration_count,
                    "sentiment": conf.sentiment.label if conf.sentiment else "neutral",
                    "expected_duration": getattr(c, "expected_duration", "medium-term"),
                    "affected_business_segment": getattr(c, "affected_business_segment", ""),
                    "related_scheme": getattr(c, "related_scheme", ""),
                    "related_sector": getattr(c, "related_sector", ""),
                }
                for c, conf in scored_catalysts
            ],
            setups=setups,
            source_errors=source_errors,
            summary=f"{len(material_catalysts)} material catalysts and {len(setups)} setups generated."
        )
        report = report_obj.to_dict()

        self.save_report(report, self.root)

        try:
            self.db.save_run(
                generated_at=generated_time,
                catalysts=report.get("catalysts", []),
                setups=setups,
                source_errors=source_errors,
                summary=report.get("summary", ""),
            )
            logger.info("Pipeline run saved to database")
        except Exception as exc:
            logger.warning(f"Failed to save run to database: {exc}")

        if send:
            self.send_alert(material_catalysts, setups, self.root)

        return report