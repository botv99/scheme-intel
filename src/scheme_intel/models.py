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
    sentiment: Optional[float] = None


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
    # Technical detail (volume breakout, MACD filter, weekly multi-timeframe).
    prior_high20: Optional[float] = None
    breakout: bool = False
    volume_avg: Optional[float] = None
    volume_ratio: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    week_trend: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceQuality:
    name: str
    url: str
    success_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    last_success_at: Optional[datetime] = None

    @property
    def reliability_score(self) -> float:
        total = self.success_count + self.error_count
        if total == 0:
            return 1.0
        return round(self.success_count / total, 2)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "reliability_score": self.reliability_score,
            "last_error": self.last_error,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
        }


@dataclass
class AnalysisReport:
    generated_at: str
    catalysts: list[dict]
    setups: list[dict]
    source_errors: list[dict]
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


