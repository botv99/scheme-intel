"""
Consolidated GOBARdhan scheme alert runner.

Runs all data sources, generates per-stock alerts with technical indicators,
evaluates swing setups for each stock, and sends a final consolidated
Telegram digest with trade recommendations.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import load_config as _load_config
from .logger import get_logger
from .notifier import send_telegram
from .pipeline import Pipeline
from .signals import make_setup
from .trade_call import (
    TradeCall,
    evaluate_setup,
    format_final_digest_telegram,
    format_trade_call_telegram,
)
from .watchlist_alerts import (
    build_message,
    get_block_deal_news,
    get_events,
    get_news,
    get_price,
    load_watchlist,
    truncate_message,
)

logger = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]


def run_all(send: bool = False, config_path: Optional[Path | str] = None) -> dict:
    """
    Execute the full consolidated workflow:

    1. Run the core pipeline (catalysts + setups)
    2. Run watchlist alerts (price, events, news per stock)
    3. Generate trade recommendations (entry/exit/holding)
    4. Send final consolidated Telegram digest

    Returns a summary dict of all actions taken.
    """
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stocks_processed": 0,
        "stocks_succeeded": 0,
        "stocks_failed": 0,
        "trade_calls": [],
        "pipeline_result": None,
        "digest_sent": False,
        "errors": [],
    }

    # ----------------------------------------------------------------
    # Step 1: Run the core pipeline (catalysts, setups, DB save)
    # ----------------------------------------------------------------
    logger.info("Step 1: Running core pipeline...")
    try:
        pipeline_result = Pipeline(config_path=config_path).run(send=False)
        result["pipeline_result"] = pipeline_result
        logger.info(
            "Pipeline complete: %d catalysts, %d setups",
            len(pipeline_result.get("catalysts", [])),
            len(pipeline_result.get("setups", [])),
        )
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        result["errors"].append(f"pipeline: {exc}")

    # ----------------------------------------------------------------
    # Step 2: Run watchlist alerts (per-stock data)
    # ----------------------------------------------------------------
    logger.info("Step 2: Running watchlist alerts...")
    try:
        stocks = load_watchlist()
    except Exception as exc:
        logger.error("Failed to load watchlist: %s", exc)
        stocks = []

    trade_calls: list[TradeCall] = []

    for stock in stocks:
        name = stock["name"]
        symbol = stock.get("symbol", "")
        result["stocks_processed"] += 1

        logger.info("Processing %s...", name)

        try:
            # 2a: Price data
            price_data = get_price(stock)

            # 2b: Events / announcements
            events = get_events(stock)

            # 2c: Block deal news
            deals = get_block_deal_news(stock)

            # 2d: Financial news
            news = get_news(stock)

            # 2e: Build and send per-stock alert message
            message = build_message(
                stock=stock,
                price=price_data,
                events=events,
                deals=deals,
                news=news,
            )
            message = truncate_message(message)

            if send:
                send_telegram(message)
                logger.info("Per-stock alert sent for %s", name)

            result["stocks_succeeded"] += 1

        except Exception as exc:
            result["stocks_failed"] += 1
            result["errors"].append(f"{name}: {exc}")
            logger.error("FAILED %s: %s", name, exc)

    # ----------------------------------------------------------------
    # Step 3: Generate trade recommendations
    # ----------------------------------------------------------------
    logger.info("Step 3: Generating trade recommendations...")

    # Build setups from pipeline if available, otherwise try per-stock
    setups_generated = _generate_setups(stocks, pipeline_result)

    for setup in setups_generated:
        call = evaluate_setup(setup)
        trade_calls.append(call)
        result["trade_calls"].append(call.to_dict())

    # ----------------------------------------------------------------
    # Step 4: Send final consolidated digest
    # ----------------------------------------------------------------
    if send and trade_calls:
        logger.info("Step 4: Sending consolidated digest...")
        digest = format_final_digest_telegram(trade_calls)
        digest = truncate_message(digest)
        try:
            send_telegram(digest)
            result["digest_sent"] = True
            logger.info("Consolidated digest sent.")
        except Exception as exc:
            result["errors"].append(f"digest send: {exc}")
            logger.error("Digest send failed: %s", exc)

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    logger.info(
        "Done: %d/%d stocks, %d trade calls, digest=%s",
        result["stocks_succeeded"],
        result["stocks_processed"],
        len(trade_calls),
        result["digest_sent"],
    )

    return result


def _generate_setups(
    stocks: list[dict],
    pipeline_result: Optional[dict] = None,
) -> list:
    """
    Generate SwingSetup objects for each stock.

    Uses pipeline setups if available (from DB), otherwise fetches
    history via yfinance and scores with make_setup().
    """
    from .models import SwingSetup

    setups = []

    # Check if pipeline returned setups
    pipeline_setups = []
    if pipeline_result:
        raw = pipeline_result.get("setups", [])
        for s in raw:
            if isinstance(s, SwingSetup):
                pipeline_setups.append(s)
            elif isinstance(s, dict):
                try:
                    pipeline_setups.append(SwingSetup(**s))
                except Exception:
                    pass

    # Map by company name for quick lookup
    pipeline_by_name = {s.company: s for s in pipeline_setups}

    for stock in stocks:
        name = stock["name"]
        symbol = stock.get("symbol", "")

        # Use pipeline setup if available
        if name in pipeline_by_name:
            setups.append(pipeline_by_name[name])
            continue

        # Otherwise try to generate one
        try:
            yahoo_sym = _yahoo_symbol(stock)
            if not yahoo_sym:
                continue

            setup = make_setup(
                company=name,
                symbol=yahoo_sym,
                catalyst_score=50,  # default when no pipeline catalyst
            )
            if setup:
                setups.append(setup)
        except Exception as exc:
            logger.warning("Setup generation failed for %s: %s", name, exc)

    return setups


def _yahoo_symbol(stock: dict) -> str | None:
    """Convert NSE/BSE symbol to Yahoo Finance symbol."""
    symbol = stock.get("symbol", "").strip()
    if not symbol:
        return None
    exchange = stock.get("exchange", "NSE").upper()
    if exchange == "NSE":
        return f"{symbol}.NS"
    if exchange == "BSE":
        return f"{symbol}.BO"
    return symbol


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="GOBARdhan consolidated scheme alert"
    )
    parser.add_argument(
        "--send", action="store_true",
        help="Send Telegram alerts (requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to custom watchlist.yaml",
    )
    args = parser.parse_args()

    result = run_all(send=args.send, config_path=args.config)
    print(json.dumps(result, indent=2))
