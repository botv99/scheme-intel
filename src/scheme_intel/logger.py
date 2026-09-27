"""
Logging configuration for scheme-intel.
Provides structured logging across all modules.
"""
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone

# Log file path with timestamp — created lazily, not at import time
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FILE = LOG_DIR / f"scheme-intel-{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"

# Track loggers we've already configured to avoid handler duplication
_configured_loggers: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    if name not in _configured_loggers:
        _configured_loggers.add(name)
        logger.setLevel(logging.DEBUG)
        # Prevent propagation to root logger to avoid duplicate lines
        logger.propagate = False
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler - DEBUG level (only if directory is writable)
        try:
            LOG_DIR.mkdir(exist_ok=True)
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8", errors="replace")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            # Read-only filesystem (CI, Lambda, etc.) — skip file logging
            pass
        
        # Console handler - INFO level
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger
