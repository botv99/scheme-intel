"""
Stage 1 Pipeline Runner.
Catalyst scanning and rule-based trade calls.
"""
from __future__ import annotations

from . import (
    Pipeline,
    AnalysisReport,
    Article,
    INGESTED_MAX_AGE_HOURS,
    IST,
    today_ist,
    article_is_today,
    fetch_rss,
    scan_page,
    deduplicate_articles,
    make_setup,
    classify,
)

__all__ = ["Pipeline"]
