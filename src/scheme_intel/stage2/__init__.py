"""
Stage 2: Daily Stock Intelligence & Adversarial Swing-Setup System
After-Market Preparation Engine.
"""
from __future__ import annotations

__version__ = "2.0.0"

from .models import (
    Stock, NewsItem, CatalystImpact, TechnicalSnapshot, DailyStockCard,
    CandidateSetup, EvidenceItem, BullThesis, BearThesis, DebateRound,
    DebateResult, RiskAssessment, WaitCondition, TradeSetup, SetupOutcome,
)
from .calendar import get_next_trading_day, get_market_session_info, MarketSessionInfo, is_trading_day
from .pipeline import Stage2Pipeline
from .market import MarketDataEngine, build_technical_snapshot
from .news import NewsEngine, classify_news_item, extract_stock_news
from .impact import score_catalyst_impact, evaluate_stock_catalysts
from .candidate import find_candidate_setup
from .scanner import scan_all_stocks
from .debate import DebateOrchestrator
from .risk import evaluate_risk
from .waiting import generate_wait_condition
from .storage import Stage2Database
from .telegram import build_full_telegram_report

__all__ = [
    "Stock",
    "NewsItem",
    "CatalystImpact",
    "TechnicalSnapshot",
    "DailyStockCard",
    "CandidateSetup",
    "EvidenceItem",
    "BullThesis",
    "BearThesis",
    "DebateRound",
    "DebateResult",
    "RiskAssessment",
    "WaitCondition",
    "TradeSetup",
    "SetupOutcome",
    "MarketSessionInfo",
    "get_next_trading_day",
    "get_market_session_info",
    "is_trading_day",
    "Stage2Pipeline",
    "MarketDataEngine",
    "build_technical_snapshot",
    "NewsEngine",
    "classify_news_item",
    "extract_stock_news",
    "score_catalyst_impact",
    "evaluate_stock_catalysts",
    "find_candidate_setup",
    "scan_all_stocks",
    "DebateOrchestrator",
    "evaluate_risk",
    "generate_wait_condition",
    "Stage2Database",
    "build_full_telegram_report",
]
