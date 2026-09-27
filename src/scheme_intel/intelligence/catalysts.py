"""
Catalyst Extraction & Scoring Module.
"""
from __future__ import annotations

from ..catalyst import classify
from ..models import Catalyst

def extract_catalysts(articles: list, companies: list[dict]) -> list[Catalyst]:
    """Extract and classify catalysts from a list of articles."""
    return [item for a in articles if (item := classify(a, companies))]

def score_catalyst(catalyst: Catalyst) -> int:
    """Return the catalyst score."""
    return catalyst.score if catalyst else 0

__all__ = ["classify", "extract_catalysts", "score_catalyst"]
