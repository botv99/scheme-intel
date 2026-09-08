from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    published_at: Optional[datetime]
    summary: str = ""


@dataclass(frozen=True)
class Catalyst:
    article: Article
    score: int
    category: str
    rationale: str
    companies: tuple[str, ...]


@dataclass(frozen=True)
class SwingSetup:
    company: str
    symbol: str
    close: float
    entry: float
    stop: float
    target: float
    rsi14: float
    catalyst_score: int
    status: str
    generated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


