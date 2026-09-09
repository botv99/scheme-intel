from __future__ import annotations

import yaml
from pathlib import Path
from typing import Optional

from .logger import get_logger
from .exceptions import ConfigurationError

logger = get_logger(__name__)


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
    root = Path(__file__).resolve().parents[2]  # project root
    path = Path(config_path) if config_path else (root / "config" / "watchlist.yaml")
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
