from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .config import load_config as _load_config
from .pipeline import Pipeline

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
    return _load_config(config_path)


def run(send: bool = False, config_path: Optional[Path | str] = None) -> dict:
    """
    Execute full scheme monitor pipeline:

    1. Optionally consume the ingested snapshot (news/announcements -> catalysts,
       OHLC history -> setups) written by the ingestion layer
    2. Scan configured sources (RSS or HTML pages)
    3. Extract and score policy/contract catalysts
    4. Calculate swing trading setups for matched stocks
    5. Save snapshot to data/latest.json
    6. Optionally send Telegram alert

    Args:
        send: Whether to send alerts via Telegram if secrets exist
        config_path: Optional custom config file path

    Returns:
        Report dictionary containing catalysts, setups, and source errors
    """
    return Pipeline(config_path=config_path).run(send=send)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scheme Intel - Monitor and Alerting Pipeline")
    parser.add_argument("--send", action="store_true", help="send material alerts when Telegram secrets are configured")
    parser.add_argument("--config", type=str, default=None, help="path to custom watchlist.yaml configuration")
    args = parser.parse_args()

    result = run(send=args.send, config_path=args.config)
    print(json.dumps(result, indent=2))