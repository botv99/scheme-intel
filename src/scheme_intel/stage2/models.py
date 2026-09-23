"""
Pydantic contracts and data models for Stage 2: Daily Stock Intelligence
and Adversarial Swing Setup System.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Stock(BaseModel):
    name: str
    symbol: str
    aliases: List[str] = Field(default_factory=list)
    screener_id: Optional[str] = None
    sectors: List[str] = Field(default_factory=list)


class NewsItem(BaseModel):
    title: str
    url: str = ""
    source: str = ""
    source_tier: int = 3
    published_at: Optional[str] = None
    summary: str = ""
    sentiment: str = "neutral"  # positive, negative, neutral
    category: str = "General"
    materiality: int = 50
    companies_mentioned: List[str] = Field(default_factory=list)


class CatalystImpact(BaseModel):
    company: str
    catalyst_name: str
    beneficiary_type: str = "Direct"  # Direct, Indirect, Neutral, Negative
    strength: int = 70
    duration: str = "medium-term"  # short-term, medium-term, long-term
    certainty: str = "High"  # High, Medium, Low
    is_fresh: bool = True
    already_priced_in: bool = False
    rationale: str = ""


class TechnicalSnapshot(BaseModel):
    # Price
    close: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    prev_close: float = 0.0
    day_change_pct: float = 0.0
    gap_pct: float = 0.0
    performance_5d: float = 0.0
    performance_20d: float = 0.0
    performance_1m: float = 0.0
    performance_3m: float = 0.0

    # Volume
    volume: float = 0.0
    volume_20d_avg: float = 0.0
    volume_50d_avg: float = 0.0
    volume_ratio: float = 1.0  # Today / 20d avg
    relative_volume: float = 1.0

    # Trend Moving Averages
    sma20: float = 0.0
    sma50: float = 0.0
    sma100: Optional[float] = None
    sma200: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None

    # Momentum & Volatility
    rsi14: float = 50.0
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    roc10: Optional[float] = None
    roc21: Optional[float] = None
    atr14: float = 0.0
    atr_pct: float = 0.0
    volatility_regime: str = "NORMAL"  # LOW, NORMAL, HIGH, EXTREME
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    adx14: Optional[float] = None

    # Structure & Levels
    high_20d: float = 0.0
    high_50d: float = 0.0
    support: float = 0.0
    resistance: float = 0.0
    swing_high: float = 0.0
    swing_low: float = 0.0

    # Relative Strength
    relative_strength_nifty: Optional[float] = None
    relative_strength_sector: Optional[float] = None
    trend_status: str = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL


class DailyStockCard(BaseModel):
    stock: Stock
    price: float
    day_change_pct: float
    volume: float = 0.0
    volume_avg_20d: float = 0.0
    volume_ratio: float = 1.0
    developments: List[str] = Field(default_factory=list)
    catalysts: List[str] = Field(default_factory=list)
    catalyst_direction: str = "Neutral"  # Bullish, Bearish, Neutral
    catalyst_strength: int = 50
    technical_summary: str = ""
    support: float = 0.0
    resistance: float = 0.0
    trend: str = "Neutral"
    tomorrow_status: str = "WAIT"  # QUALIFIED_SETUP, WATCH, WAIT, NO_TRADE


class CandidateSetup(BaseModel):
    stock: Stock
    archetype: str  # Breakout, Breakout Anticipation, Pullback, Momentum Continuation, Event-Driven
    score: int
    rationale: str
    technicals: TechnicalSnapshot
    catalysts: List[CatalystImpact] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    evidence_id: str
    claim: str
    source: str
    source_tier: int = 3
    date: str = ""
    relevance: str = "Direct"
    verified: bool = True
    confidence_weight: float = 1.0


class BullThesis(BaseModel):
    symbol: str
    company: str
    core_thesis: str
    technical_arguments: List[str] = Field(default_factory=list)
    catalyst_arguments: List[str] = Field(default_factory=list)
    fundamental_arguments: List[str] = Field(default_factory=list)
    market_arguments: List[str] = Field(default_factory=list)
    proposed_entry: str = ""
    expected_target: float = 0.0
    invalidation_level: float = 0.0
    evidence_ids: List[str] = Field(default_factory=list)
    key_risks_acknowledged: List[str] = Field(default_factory=list)


class BearThesis(BaseModel):
    symbol: str
    company: str
    core_thesis: str
    technical_flaws: List[str] = Field(default_factory=list)
    catalyst_flaws: List[str] = Field(default_factory=list)
    fundamental_flaws: List[str] = Field(default_factory=list)
    market_risks: List[str] = Field(default_factory=list)
    trade_structure_flaws: List[str] = Field(default_factory=list)
    what_would_invalidate_bear: str = ""  # Signal that proves bear thesis wrong (e.g. decisive break above resistance)
    required_confirmation_to_buy: str = ""
    evidence_ids: List[str] = Field(default_factory=list)


class DebateRound(BaseModel):
    round_num: int
    speaker: str  # BULL, BEAR, ARBITRATOR
    content: str
    evidence_cited: List[str] = Field(default_factory=list)


class DebateResult(BaseModel):
    symbol: str
    rounds: List[DebateRound] = Field(default_factory=list)
    bull_strength: float = 0.0  # 0 to 100
    bear_strength: float = 0.0  # 0 to 100
    agreed_points: List[str] = Field(default_factory=list)
    disputed_points: List[str] = Field(default_factory=list)
    resolved_claims: List[str] = Field(default_factory=list)
    key_catalyst: str = ""
    key_risk: str = ""
    confirmation_needed: str = ""


class RiskAssessment(BaseModel):
    passed: bool
    veto_reason: Optional[str] = None
    entry_min: float
    entry_max: float
    ideal_entry: float
    max_acceptable_entry: float = 0.0
    min_rr_at_max_entry: float = 1.5
    trigger_condition: str = ""
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    expected_holding_period: str = "5–15 sessions"
    risk_reward_ratio: float
    rr_basis: str = ""
    risk_per_share: float = 0.0
    reward_per_share: float = 0.0
    technical_invalidation: str = ""
    breakout_failure_condition: str = ""
    share_quantity: int = 0
    capital_deployed: float = 0.0
    position_size_pct: float = 5.0
    maximum_loss_at_stop: float = 0.0
    actual_risk_pct: float = 1.0
    volume_to_watch: str = ">1.5x 20D average"
    portfolio_capital: float = 1_000_000.0
    max_portfolio_risk_pct: float = 1.0


class WaitCondition(BaseModel):
    symbol: str
    current_price: float
    current_status: str = "WAIT"
    why_not_ready: str
    exact_price_confirmation: str = ""
    exact_volume_confirmation: str = ">1.4x 20D average"
    exact_confirmation_required: List[str] = Field(default_factory=list)
    trigger_price: float = 0.0
    volume_trigger: str = ">1.4x 20D average"
    invalidation_level: float = 0.0
    technical_invalidation_floor: str = ""
    catalyst_remaining_valid: str = "Active policy scheme tailwind"
    potential_entry: str = ""


class TradeSetup(BaseModel):
    setup_id: str
    analysis_date: str
    setup_date: str
    next_trading_session: str
    market_close_timestamp: str = ""
    stock: Stock
    status: str  # QUALIFIED_SETUP, WAIT, WATCH, NO_TRADE
    candidate: Optional[CandidateSetup] = None
    bull_thesis: Optional[BullThesis] = None
    bear_thesis: Optional[BearThesis] = None
    debate: Optional[DebateResult] = None
    risk: Optional[RiskAssessment] = None
    wait_conditions: Optional[WaitCondition] = None
    no_trade_reason: Optional[str] = None
    telegram_card: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SetupOutcome(BaseModel):
    setup_id: str
    symbol: str
    entry_triggered: bool = False
    actual_entry_price: Optional[float] = None
    entry_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    mfe_pct: float = 0.0  # Maximum Favorable Excursion
    mae_pct: float = 0.0  # Maximum Adverse Excursion
    realized_pnl_pct: Optional[float] = None
    target_hit: bool = False
    stop_hit: bool = False
    holding_period_days: int = 0
