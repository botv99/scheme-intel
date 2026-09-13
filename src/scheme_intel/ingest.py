"""
Ingestion layer runner.

Collects daily market data for the watchlist and saves it to ``data/ingested.json``:

  * screener.in        -> per-stock price snapshot (close, volume, change %,
                          RSI-14, 52-week range, market cap)
  * NSE / BSE          -> bulk/block deals and tender/contract announcements
  * Mint / Financial   -> news mentioning watchlist companies
    Express / Moneycontrol

Run locally:
    PYTHONPATH=src python -m scheme_intel.ingest
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .ingestion.exchanges import collect_exchange_activity
from .ingestion.media import collect_news
from .ingestion.models import IngestionResult
from .ingestion.price import collect_prices
from .logger import get_logger
from .models import now_utc

logger = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def ingest(config_path: Path | str | None = None, days_back: int | None = None) -> dict:
    """
    Run the full ingestion pipeline and persist the snapshot.

    Args:
        config_path: Optional custom watchlist configuration path.
        days_back: Keep exchange activity from the last N days.

    Returns:
        Ingestion report as a dictionary (also written to data/ingested.json).
    """
    config = load_config(config_path)

    prices = collect_prices(config)
    bulk_deals, announcements, exchange_errors = collect_exchange_activity(config, days_back=days_back)
    news, news_errors = collect_news(config)

    source_errors = exchange_errors + news_errors
    result = IngestionResult(
        generated_at=now_utc().isoformat(),
        prices=prices,
        bulk_deals=bulk_deals,
        announcements=announcements,
        news=news,
        source_errors=source_errors,
        summary=(
            f"{len(prices)} price snapshots, {len(bulk_deals)} bulk/block deals, "
            f"{len(announcements)} tender/contract announcements, {len(news)} news items"
        ),
    )
    report = result.to_dict()

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "ingested.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Saved ingestion snapshot to {data_dir / 'ingested.json'}")

    if source_errors:
        for error in source_errors:
            logger.warning(f"Source error: {error['source']} -> {error['error']}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheme Intel - Ingestion Layer")
    parser.add_argument("--config", type=str, default=None,
                        help="path to custom watchlist.yaml configuration")
    parser.add_argument("--days-back", type=int, default=None,
                        help="keep exchange deals/announcements from the last N days")
    args = parser.parse_args()

    report = ingest(config_path=args.config, days_back=args.days_back)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()