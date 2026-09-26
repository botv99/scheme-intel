"""
Response Formatter for Asynchronous Deep Research Results.
Formats research evidence, findings, affected companies, and sources into clean Markdown.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def format_research_acknowledgement(job_id: str) -> str:
    """Immediate acknowledgement returned to Telegram without blocking on research."""
    return (
        "🔎 *Research request received.*\n\n"
        "I'll investigate this using Scheme-Intel's verified sources and send you the researched intelligence when the analysis is complete.\n\n"
        f"• *Research ID:* `{job_id}`\n"
        "• *Status:* `QUEUED`"
    )


def format_research_result(
    job_id: str,
    question: str,
    findings: str,
    why_it_matters: str = "",
    companies_affected: Optional[List[str]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    completed_at: str = "",
) -> str:
    """Format completed research response."""
    lines = [
        "🔎 *RESEARCH COMPLETE*",
        "",
        f"*Research ID:* `{job_id}`",
        f"*Question:* {question}",
        "",
        "*FINDINGS*",
        findings.strip(),
    ]

    if why_it_matters.strip():
        lines.extend([
            "",
            "*WHY IT MATTERS*",
            why_it_matters.strip(),
        ])

    if companies_affected:
        lines.extend([
            "",
            "*COMPANIES AFFECTED*",
        ])
        for c in companies_affected:
            lines.append(f"• {c}")

    if evidence:
        lines.extend([
            "",
            "*EVIDENCE & SOURCES*",
        ])
        for ev in evidence[:5]:
            src = ev.get("source", "Source")
            title = ev.get("title", "Reference")
            date = f" — {ev['date']}" if ev.get("date") else ""
            lines.append(f"• {src}: {title[:80]}{date}")

    if completed_at:
        lines.extend([
            "",
            f"_Research completed: {completed_at[:16]} UTC_",
        ])

    return "\n".join(lines)


def format_research_failure(job_id: str, question: str, error: str) -> str:
    """Format failure report for a research task."""
    return (
        "⚠️ *RESEARCH INVESTIGATION INCOMPLETE*\n\n"
        f"• *Research ID:* `{job_id}`\n"
        f"• *Question:* {question}\n\n"
        f"Could not complete research: {error}\n\n"
        "_Please verify the query or try again later._"
    )
