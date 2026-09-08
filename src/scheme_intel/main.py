from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import yaml

from .catalyst import classify
from .exceptions import ConfigurationError, SourceAccessError, DataParseError, TelegramError
from .logger import get_logger
from .models import AnalysisReport, now_utc
from .notifier import send_telegram, validate_telegram_config
from .signals import make_setup
from .sources import deduplicate_articles, fetch_rss, scan_page

logger = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def load_config(config_path: Optional[Path | str] = None) -> dict:
    """
    Load and validate watchlist configuration from YAML.
    
    Args:
        config_path: Optional path to config file (defaults to config/watchlist.yaml)
        
    Returns:
        Dictionary containing configuration
        
    Raises:
        ConfigurationError: If configuration file is missing or invalid
    """
    path = Path(config_path) if config_path else (ROOT / "config" / "watchlist.yaml")
    if not path.exists():
        logger.error(f"Configuration file not found at {path}")
        raise ConfigurationError(f"Configuration file not found: {path}")
    
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(content, dict):
            raise ConfigurationError("Configuration file must contain a YAML mapping")
        if "scheme" not in content or "stocks" not in content:
            raise ConfigurationError("Configuration missing required 'scheme' or 'stocks' sections")
        logger.info(f"Loaded configuration for scheme '{content['scheme'].get('name', 'Unknown')}'")
        return content
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML configuration: {e}")
        raise ConfigurationError(f"Invalid YAML in configuration: {e}") from e


def run(send: bool = False, config_path: Optional[Path | str] = None) -> dict:
    """
    Execute full scheme monitor pipeline:
    1. Scan configured sources (RSS or HTML pages)
    2. Extract and score policy/contract catalysts
    3. Calculate swing trading setups for matched stocks
    4. Save snapshot to data/latest.json
    5. Optionally send Telegram alert
    
    Args:
        send: Whether to send alerts via Telegram if secrets exist
        config_path: Optional custom config file path
        
    Returns:
        Report dictionary containing catalysts, setups, and source errors
    """
    logger.info("Starting scheme-intel scan run...")
    config = load_config(config_path)
    
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
    
    catalysts = [item for article in deduped if (item := classify(article, config["stocks"]))]
    min_score = config.get("settings", {}).get("minimum_catalyst_score", 60)
    material = [item for item in catalysts if item.score >= min_score]
    logger.info(f"Classified {len(catalysts)} catalysts ({len(material)} material with score >= {min_score})")
    
    setups = []
    for catalyst in material:
        for company in config["stocks"]:
            if company["name"] in catalyst.companies and company.get("symbol"):
                try:
                    setup = make_setup(company["name"], company["symbol"], catalyst.score)
                    if setup:
                        setups.append(setup.to_dict())
                        logger.info(f"Generated {setup.status} setup for {company['name']} ({company['symbol']})")
                except Exception as e:
                    logger.error(f"Failed to generate setup for {company['name']}: {e}")
                    
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
            for c in material
        ],
        setups=setups,
        source_errors=source_errors,
        summary=f"{len(material)} material catalysts and {len(setups)} setups generated."
    )
    report = report_obj.to_dict()
    
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Saved latest report snapshot to {data_dir / 'latest.json'}")
    
    if send and material:
        if validate_telegram_config():
            lines = ["GOBARdhan / CBG catalyst alert"]
            lines.extend(f"• [{c.score}] {c.article.title}\n{c.article.url}" for c in material)
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
            
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scheme Intel - Monitor and Alerting Pipeline")
    parser.add_argument("--send", action="store_true", help="send material alerts when Telegram secrets are configured")
    parser.add_argument("--config", type=str, default=None, help="path to custom watchlist.yaml configuration")
    args = parser.parse_args()
    
    result = run(send=args.send, config_path=args.config)
    print(json.dumps(result, indent=2))

