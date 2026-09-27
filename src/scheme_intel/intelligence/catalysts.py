"""
Catalyst Extraction & Scoring Module.
Provides extraction, classification, and scoring utilities for market catalysts.
"""
from __future__ import annotations

from typing import List, Optional, Union
from ..catalyst import classify
from ..models import Article, Catalyst


def extract_catalysts(
    article_or_articles: Union[Article, List[Article]],
    companies: list[dict],
) -> List[Catalyst]:
    """Extract and classify catalysts from an article or list of articles."""
    if isinstance(article_or_articles, list):
        return [item for a in article_or_articles if (item := classify(a, companies))]
    c = classify(article_or_articles, companies)
    return [c] if c else []


def score_catalyst(catalyst: Optional[Catalyst]) -> int:
    """Return integer score of the catalyst."""
    return int(catalyst.score) if catalyst and catalyst.score is not None else 0


__all__ = ["extract_catalysts", "score_catalyst", "classify"]
