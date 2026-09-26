"""
Telegram Alert Delivery Engine.
Handles throttled broadcast dispatch of Stage 2 daily intelligence reports.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from ..notifier import send_telegram
from ..logger import get_logger

logger = get_logger(__name__)


def chunk_message(text: str, max_chars: int = 4000) -> List[str]:
    """Split a long markdown message into chunk sizes acceptable to Telegram (<= 4096 chars)."""
    if len(text) <= max_chars:
        return [text]
    lines = text.split("\n")
    chunks = []
    current = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = [line]
                current_len = len(line) + 1
            else:
                chunks.append(line[:max_chars])
                current = [line[max_chars:]]
                current_len = len(line[max_chars:]) + 1
        else:
            current.append(line)
            current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def dispatch_daily_report(
    report: Dict[str, str],
    outcome_updates: Optional[Dict[str, Any]] = None,
    perf_summary: Optional[str] = None,
) -> None:
    """Send complete multi-section report to Telegram with rate limit handling."""
    logger.info("Dispatching daily intelligence report to Telegram...")
    sections = [
        ("Section 1: Daily Intelligence", report.get("section1", "")),
        ("Section 2: Swing Radar", report.get("section2", "")),
        ("Section 3: Actionable & Waiting Setups", report.get("section3", "")),
    ]

    outcome_text = outcome_updates.get("summary_text", "") if outcome_updates else ""
    if perf_summary:
        if outcome_text:
            outcome_text = f"{outcome_text}\n\n{perf_summary}"
        else:
            outcome_text = perf_summary

    if outcome_text.strip():
        sections.append(("Active Positions & Outcome Tracker", outcome_text))

    for name, text in sections:
        if not text.strip():
            continue
        chunks = chunk_message(text, max_chars=4000)
        for chunk in chunks:
            try:
                success = send_telegram(chunk, parse_mode="Markdown")
                if success:
                    logger.info("Successfully sent %s chunk (%d chars) to Telegram", name, len(chunk))
                else:
                    logger.warning("Telegram notification skipped or secrets not configured for %s", name)
            except Exception as e:
                logger.error("Error sending %s to Telegram: %s", name, e)
            time.sleep(1.2)
