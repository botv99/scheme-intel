"""
Response Formatter for Scheme-Intel Deep Multi-Agent Research Results (Stage 3).
Formats verified intelligence, adversarial Bull/Bear analysis, Arbiter verdict, and sources.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def format_research_acknowledgement(job_id: str, question: str = "") -> str:
    """Immediate acknowledgement returned to Telegram."""
    return (
        "🔬 *DEEP RESEARCH STARTED*\n\n"
        "*Request ID:*\n"
        f"`{job_id}`\n\n"
        "Your research is being analyzed by the Scheme-Intel intelligence engine.\n\n"
        "This may take a little time."
    )


def format_research_result(
    job_id: str,
    question: str,
    bull_case: List[str],
    bear_case: List[str],
    arbiter_verdict: str,
    arbiter_why: List[str],
    arbiter_confidence: str,
    key_risk: str,
    invalidation: str,
    technical_score: Optional[float] = None,
    fundamental_score: Optional[float] = None,
    setup_status: Optional[str] = None,
    catalysts: Optional[List[str]] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
    completed_at: str = "",
) -> str:
    """Format deep multi-agent intelligence research report."""
    lines = [
        "🔬 *SCHEME-INTEL RESEARCH*",
        "",
        "*Question:*",
        question.strip(),
        "",
        "━━━━━━━━━━━━━━",
        "",
        "📊 *CURRENT INTELLIGENCE*",
        "",
        f"Technical: {technical_score:.1f}/10" if technical_score is not None else "Technical: N/A",
        f"Fundamental: {fundamental_score:.1f}/10" if fundamental_score is not None else "Fundamental: N/A",
        f"Trade Setup: `{setup_status or 'WAIT'}`",
    ]

    # Catalysts
    if catalysts:
        lines.extend(["", "🔥 *CATALYST*", ""])
        for c in catalysts[:3]:
            lines.append(f"• {c}")

    # Bull Case
    lines.extend(["", "🟢 *BULL CASE*", ""])
    if bull_case:
        for b in bull_case:
            lines.append(f"• {b}")
    else:
        lines.append("• No verifiable bullish catalysts in current window.")

    # Bear Case
    lines.extend(["", "🔴 *BEAR CASE*", ""])
    if bear_case:
        for b in bear_case:
            lines.append(f"• {b}")
    else:
        lines.append("• Low structural downside evidence detected.")

    # Arbiter
    lines.extend([
        "",
        "🏛️ *ARBITER*",
        "",
        f"*Verdict:* `{arbiter_verdict.upper()}`",
        "",
        "*Why:*",
    ])
    if arbiter_why:
        for w in arbiter_why:
            lines.append(f"• {w}")
    else:
        lines.append(f"• Evidence balance currently supports {arbiter_verdict.upper()} stance.")

    lines.extend([
        "",
        f"*Confidence:* `{arbiter_confidence.upper()}`",
        "",
        "⚠️ *KEY RISK*",
        key_risk.strip() if key_risk else "Regulatory shift or broader market downside contagion.",
        "",
        "🧭 *WHAT WOULD CHANGE THE VIEW*",
        invalidation.strip() if invalidation else "Material volume-backed price reversal or official policy revision.",
    ])

    # Sources
    if sources:
        lines.extend(["", "📰 *SOURCES*", ""])
        for s in sources[:4]:
            name = s.get("source") or "Official Disclosure"
            title = s.get("title") or s.get("name") or "Filing"
            date = f" ({s['date']})" if s.get("date") else ""
            url = f"\n  {s['url']}" if s.get("url") else ""
            lines.append(f"• {name}: {title[:75]}{date}{url}")

    lines.extend([
        "",
        "━━━━━━━━━━━━━━",
        "",
        "*Research ID:*",
        f"`{job_id}`",
        "",
        f"*Completed:* {completed_at[:16].replace('T', ' ')} UTC" if completed_at else f"*Completed:* {job_id}",
    ])

    return "\n".join(lines)


def format_research_failure(job_id: str, reason: str = "AI providers unavailable.") -> str:
    """Format research failure report."""
    return (
        "⚠️ *Research could not be completed.*\n\n"
        f"*Reason:*\n{reason}\n\n"
        f"*Request ID:*\n`{job_id}`"
    )
