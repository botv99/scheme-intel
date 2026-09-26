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


def run(
    send: bool = False,
    config_path: Optional[Path | str] = None,
    stage: int = 2,
    provider: str = "auto",
) -> dict:
    """
    Execute full scheme monitor pipeline:

    1. Optionally consume the ingested snapshot (news/announcements -> catalysts,
       OHLC history -> setups) written by the ingestion layer
    2. Scan configured sources (RSS or HTML pages)
    3. Extract and score policy/contract catalysts
    4. Calculate swing trading setups for matched stocks
    5. Save snapshot to data/latest.json
    6. When stage=2, execute Stage 2 After-Market Swing Preparation Engine
       (100% watchlist scan, dual-agent debate, hard risk engine veto, outcome tracker)
    7. Optionally send Telegram alerts

    Args:
        send: Whether to send alerts via Telegram if secrets exist
        config_path: Optional custom config file path
        stage: 1 for Stage 1 only, 2 for Unified Stage 1 + Stage 2 (default)
        provider: LLM provider for Stage 2 (gemini, openai, mock)

    Returns:
        Report dictionary containing catalysts, setups, source errors, and stage2 results
    """
    stage1_pipeline = Pipeline(config_path=config_path)
    # If stage=2, stage1 doesn't send duplicate alerts; stage2 handles full authoritative dispatch
    stage1_send = send if stage == 1 else False
    report = stage1_pipeline.run(send=stage1_send)

    if stage == 2:
        try:
            from .stage2.pipeline import Stage2Pipeline, get_llm_provider
            llm = get_llm_provider(provider)
            cfg_str = str(config_path) if config_path else None
            stage2_pipeline = Stage2Pipeline(provider=llm, config_path=cfg_str, mode="production")
            stage2_result = stage2_pipeline.run(send=send)
            report["stage2"] = stage2_result
        except Exception as e:
            # Fallback gracefully so pipeline never hard crashes on stage 2 errors
            report["stage2_error"] = str(e)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scheme Intel - Monitor and Alerting Pipeline")
    parser.add_argument("--send", action="store_true", help="send material alerts when Telegram secrets are configured")
    parser.add_argument("--config", type=str, default=None, help="path to custom watchlist.yaml configuration")
    parser.add_argument("--stage", type=int, default=2, choices=[1, 2], help="pipeline stage to execute (1 or 2, default: 2)")
    parser.add_argument("--provider", type=str, default="auto", help="LLM Provider for Stage 2 (auto, gemini, groq, openrouter, openai, mock)")
    args = parser.parse_args()

    result = run(send=args.send, config_path=args.config, stage=args.stage, provider=args.provider)
    print(json.dumps(result, indent=2, default=str))