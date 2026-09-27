"""
Catalyst Extraction & Scoring Module.
"""
from __future__ import annotations

from typing import List, Optional
from ..catalyst import classify
from ..models import Article, Catalyst


def extract_catalysts(article: Article, companies: list[dict]) -> List[Catalyst]:
    c = classify(article, companies)
    return [c] if c else []


def score_catalyst(catalyst: Catalyst) -> int:
    return int(catalyst.score) if catalyst else 0


__all__ = ["extract_catalysts", "score_catalyst", "classify"]
