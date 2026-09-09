from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .catalyst import classify
from .exceptions import ConfigurationError, SourceAccessError, DataParseError, TelegramError
from .logger import get_logger
from .models import AnalysisReport, now_utc
from .notifier import send_telegram, validate_telegram_config
from .signals import make_setup
from .sources import deduplicate_articles, fetch_rss, scan_page
from .config import load_config

logger = get_logger(__name__)


class Pipeline:
    """
    Core pipeline that runs the full Scheme Intel workflow.
    """

    def __init__(self, config_path: Optional[Path | str] = None):
        self.config_path = config_path
        self.config: dict | None = None

    def load_config(self) -> dict:
        """Load and validate watchlist configuration."""
        return load_config(self.config_path)

    def fetch_articles(self, config: dict) -> tuple[list, list]:
        """Fetch articles from configured sources."""
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
                logger.debug(f"Fetched {len(fetched)} articles from {name}")
            except (SourceAccessError, DataParseError) as error:
                logger.warning(f"Source failure for '{name}': {error}")
                source_errors.append({"source": name, "error": str(error)[:180]})
            except Exception as error:
                logger.error(f"Unexpected error scanning '{name}': {error}")
                source_errors.append({"source": name, "error": str(error)[:180]})

        deduped = deduplicate_articles(articles)
        logger.info(f"Total unique articles gathered: {len(deduped)}")
        return deduped, source_errors

    def detect_catalysts(self, articles: list, config: dict) -> tuple[list, list]:
        """Detect catalysts and filter material ones."""
        catalysts = [item for article in articles if (item := classify(article, config["stocks"]))]
        min_score = config.get("settings", {}).get("minimum_catalyst_score", 60)
        material = [item for item in catalysts if item.score >= min_score]
        logger.info(f"Classified {len(catalysts)} catalysts ({len(material)} material with score >= {min_score})")
        return material, catalysts

    def generate_setups(self, material_catalysts: list, config: dict) -> list:
        """Generate swing setups for material catalysts."""
        setups = []
        for catalyst in material_catalysts:
            for company in config["stocks"]:
                if company["name"] in catalyst.companies and company.get("symbol"):
                    try:
                        setup = make_setup(company["name"], company["symbol"], catalyst.score)
                        if setup:
                            setups.append(setup.to_dict())
                            logger.info(f"Generated {setup.status} setup for {company['name']} ({company['symbol']})")
                    except Exception as e:
                        logger.error(f"Failed to generate setup for {company['name']}: {e}")
        return setups

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
                lines.extend(f"• {s['company']}: entry {s['entry']}, stop {s['stop']}, target {s['target']} ({s['status']})" for s in setups)
            try:
                send_telegram("\n".join(lines))
                logger.info("Telegram notification sent successfully")
            except TelegramError as e:
                logger.error(f"Failed to send Telegram notification: {e}")
        else:
            logger.warning("Telegram send requested but credentials are not configured")

    def run(self, send: bool = False) -> dict:
        """Execute the full pipeline."""
        logger.info("Starting scheme-intel scan run...")
        self.config = self.load_config()
        articles, source_errors = self.fetch_articles(self.config)
        material_catalysts, all_catalysts = self.detect_catalysts(articles, self.config)
        setups = self.generate_setups(material_catalysts, self.config)

        generated_time = now_utc().isoformat()
        report_obj = AnalysisReport(
            generated_at=generated_time,
            catalysts=[
                {
                    "title": c.article.title,
                    "url": c.article.url,
                    "score": c.score,
                    "category": c.category,
                    "companies": c.companies,
                }
                for c in material_catalysts
            ],
            setups=setups,
            source_errors=source_errors,
            summary=f"{len(material_catalysts)} material catalysts and {len(setups)} setups generated."
        )
        report = report_obj.to_dict()

        root = Path(__file__).resolve().parents[2]
        self.save_report(report, root)

        if send:
            self.send_alert(material_catalysts, setups, root)

        return report
