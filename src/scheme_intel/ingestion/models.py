"""Data models for the ingestion layer."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class PriceSnapshot:
    """
    One stock's daily market snapshot.

    Close / volume / change % come from screener.in (primary source), open/high/low
    are enriched from Yahoo Finance when available (fallback: previous close). RSI(14)
    is computed from the screener.in daily close series.
    """

    company: str
    symbol: str
    screener_id: str
    date: Optional[str]
    open: Optional[float]
    close: Optional[float]
    high: Optional[float]
    low: Optional[float]
    volume: Optional[int]
    change_pct: Optional[float]
    rsi14: Optional[float]
    market_cap: Optional[str]
    high_52w: Optional[float]
    low_52w: Optional[float]
    price_source: str
    dma200: Optional[float] = None
    error: Optional[str] = None
    history: Optional[list[dict]] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExchangeDeal:
    """A bulk or block deal reported by NSE / BSE."""

    exchange: str
    deal_type: str  # "bulk" | "block"
    date: str
    symbol: str
    security: str
    client: str
    side: str
    quantity: float
    price: float
    remarks: str = ""
    source_url: str = ""
    in_watchlist: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Announcement:
    """A corporate announcement matching tender / contract / order keywords."""

    exchange: str
    date: str
    symbol: str
    company: str
    title: str
    url: str
    keywords: tuple[str, ...] = ()
    category: str = ""
    in_watchlist: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MediaArticle:
    """A news article about a watchlist company from the configured media sources."""

    title: str
    url: str
    source: str
    published_at: Optional[str]
    matched_stocks: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IngestionResult:
    generated_at: str
    prices: list[dict]
    bulk_deals: list[dict]
    announcements: list[dict]
    news: list[dict]
    source_errors: list[dict]
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NormalizedSchemeEvent:
    """
    Standardized cross-scheme intelligence event.
    Explicitly carries scheme_id to prevent cross-scheme contamination.
    """
    event_id: str
    scheme_id: str
    source_id: str
    title: str
    content: str
    event_type: str = "POLICY_ANNOUNCEMENT"
    summary: str = ""
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None
    entities: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    importance: str = "MEDIUM"
    confidence: float = 1.0
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SchemeIngestionBatch:
    """Ingestion batch for a specific scheme execution."""
    scheme_id: str
    run_id: str
    timestamp: str
    events: list[NormalizedSchemeEvent] = field(default_factory=list)
    source_health: dict[str, str] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)