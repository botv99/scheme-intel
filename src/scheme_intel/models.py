from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

# ------------------------------------------------------------------
# Source Hierarchy (Phase 3)
# Tier 1: Government / regulator / exchange
# Tier 2: Company official disclosure / investor relations
# Tier 3: Established financial publications
# Tier 4: Analyst / research sources
# Tier 5: Social media / unverified sources
# ------------------------------------------------------------------
TIER_1_GOV_REGULATOR = 1
TIER_2_COMPANY_DISCLOSURE = 2
TIER_3_FINANCIAL_MEDIA = 3
TIER_4_ANALYST_RESEARCH = 4
TIER_5_UNVERIFIED_SOCIAL = 5


def resolve_source_tier(source_name: str, url: str = "") -> int:
    """Classify a source into Tier 1 (highest) through Tier 5 (lowest)."""
    text = f"{source_name} {url}".lower()
    if any(k in text for k in ("pib", "gov", "nic.in", "mnre", "jal shakti", "gobardhan", "nse", "bse", "rbi", "sebi")):
        return TIER_1_GOV_REGULATOR
    if any(k in text for k in ("investor", "disclosure", "annual report", "corporate announcement", "filing")):
        return TIER_2_COMPANY_DISCLOSURE
    if any(k in text for k in ("economictimes", "economic times", "livemint", "mint", "business-standard",
                              "business standard", "financial express", "reuters", "bloomberg", "cnbc")):
        return TIER_3_FINANCIAL_MEDIA
    if any(k in text for k in ("scripbox", "brokerage", "analyst", "icici direct", "hdfc sec", "motilal", "axis sec")):
        return TIER_4_ANALYST_RESEARCH
    return TIER_3_FINANCIAL_MEDIA


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    published_at: Optional[datetime]
    summary: str = ""
    sentiment: Optional[float] = None
    source_tier: int = TIER_3_FINANCIAL_MEDIA


@dataclass(frozen=True)
class Catalyst:
    article: Article
    score: int
    category: str
    rationale: str
    companies: tuple[str, ...]
    catalyst_type: str = ""
    headline: str = ""
    published_at: Optional[str] = None
    event_date: Optional[str] = None
    confidence: float = 0.0
    sentiment_label: str = "neutral"
    expected_duration: str = "medium-term"
    affected_business_segment: str = ""
    related_scheme: str = ""
    related_sector: str = ""
    source_tier: int = TIER_3_FINANCIAL_MEDIA

    def to_dict(self) -> dict:
        return {
            "title": self.article.title if self.article else self.headline,
            "headline": self.headline or (self.article.title if self.article else ""),
            "url": self.article.url if self.article else "",
            "score": self.score,
            "category": self.category,
            "catalyst_type": self.catalyst_type or self.category,
            "rationale": self.rationale,
            "companies": list(self.companies),
            "source": self.article.source if self.article else "",
            "source_tier": self.source_tier,
            "published_at": self.published_at or (self.article.published_at.isoformat() if self.article and self.article.published_at else None),
            "event_date": self.event_date,
            "confidence": self.confidence,
            "sentiment_label": self.sentiment_label,
            "expected_duration": self.expected_duration,
            "affected_business_segment": self.affected_business_segment,
            "related_scheme": self.related_scheme,
            "related_sector": self.related_sector,
        }


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
    # Technical detail (volume breakout, MACD filter, weekly multi-timeframe, 200-DMA).
    prior_high20: Optional[float] = None
    breakout: bool = False
    volume_avg: Optional[float] = None
    volume_ratio: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    week_trend: Optional[str] = None
    dma200: Optional[float] = None
    # Expanded technical engine attributes (Phase 4)
    sma100: Optional[float] = None
    roc10: Optional[float] = None
    roc21: Optional[float] = None
    prior_high50: Optional[float] = None
    breakout_dist_pct: Optional[float] = None
    atr_pct: Optional[float] = None
    volatility_regime: Optional[str] = None
    support: Optional[float] = None
    resistance: Optional[float] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    rs_nifty: Optional[float] = None

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
