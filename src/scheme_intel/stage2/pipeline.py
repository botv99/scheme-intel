"""
Stage 2 Master Pipeline Orchestrator.
Daily Stock Intelligence + Adversarial Swing-Setup System (After-Market Preparation Engine).
Runs daily after 16:30 IST on completed market session data to prepare next-session swing setups.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .models import (
    Stock, DailyStockCard, CandidateSetup, TradeSetup, TechnicalSnapshot,
    NewsItem, WaitCondition, RiskAssessment, CatalystImpact,
    DATA_OK, DATA_UNAVAILABLE, DATA_STALE, DATA_INSUFFICIENT,
)
from .calendar import get_market_session_info, MarketSessionInfo
from .providers.base import LLMProvider
from .providers.mock import MockProvider
from .providers.gemini import GeminiProvider
from .providers.openai import OpenAIProvider
from .market import MarketDataEngine
from .news import NewsEngine
from .impact import evaluate_stock_catalysts
from .candidate import find_candidate_setup
from .scanner import scan_all_stocks
from .debate import DebateOrchestrator
from .risk import evaluate_risk
from .waiting import generate_wait_condition
from .storage import Stage2Database
from .telegram import build_full_telegram_report
from .tracker import OutcomeTracker
from ..config import load_config
from ..notifier import send_telegram
from ..logger import get_logger
import time

logger = get_logger(__name__)


def get_llm_provider(name: str = "mock") -> LLMProvider:
    """Factory for selecting LLM provider."""
    provider_lower = name.lower()
    if provider_lower == "gemini":
        try:
            p = GeminiProvider()
            if not p.api_key:
                logger.warning("GEMINI_API_KEY / GOOGLE_API_KEY not found in environment, falling back to MockProvider for debate reasoning")
                return MockProvider()
            return p
        except Exception as e:
            logger.warning("Could not initialize GeminiProvider (%s), falling back to MockProvider", e)
            return MockProvider()
    elif provider_lower == "openai":
        try:
            p = OpenAIProvider()
            if not p.api_key:
                logger.warning("OPENAI_API_KEY not found in environment, falling back to MockProvider for debate reasoning")
                return MockProvider()
            return p
        except Exception as e:
            logger.warning("Could not initialize OpenAIProvider (%s), falling back to MockProvider", e)
            return MockProvider()
    else:
        return MockProvider()


def load_watchlist_stocks(config_path: Optional[str] = None) -> List[Stock]:
    """Load stock definitions from YAML watchlist config."""
    try:
        cfg = load_config(config_path)
        raw_stocks = cfg.get("stocks", [])
        stocks: List[Stock] = []
        for s in raw_stocks:
            stock = Stock(
                name=s.get("name", ""),
                symbol=s.get("symbol", ""),
                aliases=s.get("aliases", []),
                screener_id=s.get("screener_id"),
                sectors=[s.get("sector")] if "sector" in s else ["Bioenergy", "Energy"],
            )
            stocks.append(stock)
        return stocks
    except Exception as e:
        logger.warning("Failed to load watchlist config (%s); using default watchlist", e)
        return [
            Stock(name="Praj Industries", symbol="PRAJIND.NS", aliases=["Praj", "Praj Ind"], sectors=["Bioenergy", "Capital Goods"]),
            Stock(name="TruAlt Bioenergy", symbol="TRUALT.NS", aliases=["TruAlt"], sectors=["Biofuels"]),
            Stock(name="Gulshan Polyols", symbol="GULPOLY.NS", aliases=["Gulshan"], sectors=["Ethanol"]),
            Stock(name="VA Tech Wabag", symbol="WABAG.NS", aliases=["Wabag"], sectors=["Water Infrastructure"]),
            Stock(name="Ion Exchange", symbol="IONEXCHANG.NS", aliases=["Ion Exchange"], sectors=["Water Treatment"]),
            Stock(name="BEML Ltd", symbol="BEML.NS", aliases=["BEML"], sectors=["Railways", "Defense"]),
            Stock(name="Titagarh Rail", symbol="TITAGARH.NS", aliases=["Titagarh"], sectors=["Railways"]),
        ]


class Stage2Pipeline:
    """
    Main Stage 2 After-Market Preparation Engine.
    Executes the authoritative 16:30 IST analysis cycle.
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        db_path: Optional[Path | str] = None,
        config_path: Optional[str] = None,
        market_engine: Optional[MarketDataEngine] = None,
        news_engine: Optional[NewsEngine] = None,
        mode: str = "production",
    ):
        self.mode = mode
        self.provider = provider or (MockProvider() if mode == "mock" else get_llm_provider("gemini"))
        self.db = Stage2Database(db_path)
        self.market_engine = market_engine or MarketDataEngine(mode=mode)
        self.news_engine = news_engine or NewsEngine(mode=mode)
        self.debate_orchestrator = DebateOrchestrator(self.provider)
        self.tracker = OutcomeTracker(self.db, config_path=config_path)
        self.config_path = config_path

    def run(
        self,
        target_symbol: Optional[str] = None,
        session_date: Optional[str] = None,
        dry_run: bool = False,
        send: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute full after-market intelligence & swing preparation pipeline:
        1. Determine market session & next active trading day
        2. Ingest session market data & news for 100% of watchlist stocks
        3. Score catalysts & detect setup candidates
        4. Run Dual-Agent Adversarial Debate + Hard Risk Veto on candidates
        5. Generate Actionable Triggers for waiting engine
        6. Persist to SQLite and compile 3-Section Telegram Report
        """
        if self.mode == "mock":
            self.market_engine.mode = "mock"
            self.news_engine.mode = "mock"
        # 1. Authoritative Timing & Session Info
        if session_date:
            session_info = MarketSessionInfo(
                analysis_date=session_date,
                market_close_timestamp=f"{session_date}T15:30:00+05:30",
                setup_date=session_date,
                next_trading_session=f"Next Session ({session_date})",
                is_trading_day=True,
                is_after_market_close=True,
                is_official_run_window=True,
            )
        else:
            session_info = get_market_session_info()

        logger.info(
            "=== Starting Stage 2 Pipeline: Completed Session %s -> Next Session %s ===",
            session_info.analysis_date,
            session_info.next_trading_session,
        )

        stocks = load_watchlist_stocks(self.config_path)
        if target_symbol:
            filtered = [s for s in stocks if s.symbol.upper() == target_symbol.upper() or s.name.lower() == target_symbol.lower()]
            if filtered:
                stocks = filtered
            else:
                stocks = [Stock(name=target_symbol, symbol=target_symbol, sectors=["General"])]

        # 2. Ingest Technical Snapshots for all stocks
        market_snapshots: Dict[str, TechnicalSnapshot] = {}
        data_statuses: Dict[str, str] = {}
        data_reasons: Dict[str, str] = {}

        for stock in stocks:
            try:
                snap, d_status, reason = self.market_engine.get_snapshot_with_status(
                    stock.symbol, analysis_date=session_info.analysis_date
                )
                data_statuses[stock.symbol] = d_status
                if reason:
                    data_reasons[stock.symbol] = reason
                if snap:
                    market_snapshots[stock.symbol] = snap
            except Exception as e:
                logger.warning("Error fetching technical snapshot for %s: %s", stock.symbol, e)
                data_statuses[stock.symbol] = DATA_UNAVAILABLE
                data_reasons[stock.symbol] = str(e)

        # 2b. Automated Trade Outcome Tracking for previously active setups
        outcome_updates: Optional[Dict[str, Any]] = None
        if not dry_run:
            try:
                outcome_updates = self.tracker.evaluate_active_setups(
                    market_snapshots=market_snapshots,
                    session_date=session_info.analysis_date,
                )
            except Exception as e:
                logger.warning("Error evaluating active setup outcomes: %s", e)

        # 3. Ingest News and Group by Company
        raw_news = self.news_engine.fetch_latest_news()
        stock_news = self.news_engine.group_by_stock(raw_news, stocks)

        # 4. Catalyst Impact Scoring & Candidate Detection
        candidates: Dict[str, CandidateSetup] = {}
        stock_catalysts: Dict[str, List[CatalystImpact]] = {}

        for stock in stocks:
            news_items = stock_news.get(stock.name, []) or stock_news.get(stock.symbol, [])
            snap = market_snapshots.get(stock.symbol)
            catalysts = evaluate_stock_catalysts(news_items, stock, snap)
            stock_catalysts[stock.symbol] = catalysts

            # Only evaluate candidate setup if valid market snapshot exists!
            if snap:
                cand = find_candidate_setup(stock, snap, catalysts)
                if cand:
                    candidates[stock.symbol] = cand
                    logger.info("Candidate detected for %s: %s (score: %d)", stock.symbol, cand.archetype, cand.score)

        # 5. Process Candidates through Dual Debate & Hard Risk Engine
        trade_setups: List[TradeSetup] = []
        statuses: Dict[str, str] = {}

        for stock in stocks:
            snap = market_snapshots.get(stock.symbol)
            cand = candidates.get(stock.symbol)
            d_status = data_statuses.get(stock.symbol, DATA_OK if snap else DATA_UNAVAILABLE)
            setup_id = f"SETUP-{stock.symbol.replace('.', '_')}-{session_info.analysis_date.replace('-', '')}"

            if not snap:
                # Explicit data failure handling: Never fall through to WAIT or fake triggers!
                status = d_status if d_status in (DATA_UNAVAILABLE, DATA_STALE, DATA_INSUFFICIENT) else DATA_UNAVAILABLE
                reason = data_reasons.get(stock.symbol, "No valid OHLCV history was available for this symbol.")
                setup = TradeSetup(
                    setup_id=setup_id,
                    analysis_date=session_info.analysis_date,
                    setup_date=session_info.setup_date,
                    next_trading_session=session_info.next_trading_session,
                    market_close_timestamp=session_info.market_close_timestamp,
                    stock=stock,
                    status=status,
                    data_status=status,
                    wait_conditions=None,
                    no_trade_reason=f"Market data unavailable: {reason}",
                )
            elif cand:
                # Run Adversarial Debate (Bull, Bear, Arbitrator)
                bull, bear, debate = self.debate_orchestrator.run_debate(cand)

                # Hard Risk Engine Assessment (Mathematical Veto)
                risk = evaluate_risk(cand, bull)

                # Final Status Determination: Never force a trade!
                if debate.bull_strength >= debate.bear_strength and risk.passed:
                    status = "QUALIFIED_SETUP"
                    wait_cond = None
                    no_trade_reason = None
                else:
                    status = "WAIT"
                    wait_cond = generate_wait_condition(stock, snap, cand, bear, risk)
                    no_trade_reason = risk.veto_reason if not risk.passed else "Bear stress-test prevailed; waiting for confirmation."

                setup = TradeSetup(
                    setup_id=setup_id,
                    analysis_date=session_info.analysis_date,
                    setup_date=session_info.setup_date,
                    next_trading_session=session_info.next_trading_session,
                    market_close_timestamp=session_info.market_close_timestamp,
                    stock=stock,
                    status=status,
                    data_status=DATA_OK,
                    candidate=cand,
                    bull_thesis=bull,
                    bear_thesis=bear,
                    debate=debate,
                    risk=risk,
                    wait_conditions=wait_cond,
                    no_trade_reason=no_trade_reason,
                )
            else:
                # Not a candidate: Check if WAIT or NO_TRADE
                if snap.trend_status == "BEARISH" and (not stock_catalysts.get(stock.symbol)):
                    status = "NO_TRADE"
                    wait_cond = None
                    no_trade_reason = f"Downtrend below 50 DMA (₹{snap.sma50:.1f}) with no active scheme catalysts."
                else:
                    status = "WAIT"
                    wait_cond = generate_wait_condition(stock, snap)
                    no_trade_reason = None

                setup = TradeSetup(
                    setup_id=setup_id,
                    analysis_date=session_info.analysis_date,
                    setup_date=session_info.setup_date,
                    next_trading_session=session_info.next_trading_session,
                    market_close_timestamp=session_info.market_close_timestamp,
                    stock=stock,
                    status=status,
                    data_status=DATA_OK,
                    wait_conditions=wait_cond,
                    no_trade_reason=no_trade_reason,
                )

            statuses[stock.symbol] = status
            trade_setups.append(setup)

            if not dry_run:
                self.db.save_setup(setup)

        # 6. Generate Daily Stock Intelligence Cards (100% Watchlist Coverage)
        cards = scan_all_stocks(
            stocks=stocks,
            market_data=market_snapshots,
            stock_news=stock_news,
            stock_catalysts=stock_catalysts,
            candidates=candidates,
            statuses=statuses,
            data_statuses=data_statuses,
        )

        # 7. Format 3-Section Telegram Report
        session_title = f"{session_info.analysis_date} — AFTER MARKET (Prep for {session_info.next_trading_session})"
        health_stats = {
            "total": len(stocks),
            "valid": sum(1 for st in data_statuses.values() if st == DATA_OK),
            "stale": sum(1 for st in data_statuses.values() if st == DATA_STALE),
            "unavailable": sum(1 for st in data_statuses.values() if st in (DATA_UNAVAILABLE, DATA_INSUFFICIENT)),
        }
        report = build_full_telegram_report(
            session_title=session_title,
            cards=cards,
            candidates=list(candidates.values()),
            setups=trade_setups,
            health_stats=health_stats,
        )

        # 8. Dispatch to Telegram if send=True
        if send:
            self._dispatch_telegram_report(report, outcome_updates)

        logger.info(
            "=== Stage 2 Complete: %d Scanned, %d Qualified, %d Waiting, %d No Trade, %d Data Unavailable ===",
            len(stocks),
            sum(1 for s in trade_setups if s.status == "QUALIFIED_SETUP"),
            sum(1 for s in trade_setups if s.status == "WAIT"),
            sum(1 for s in trade_setups if s.status == "NO_TRADE"),
            sum(1 for s in trade_setups if s.status in (DATA_UNAVAILABLE, DATA_STALE, DATA_INSUFFICIENT)),
        )

        return {
            "session_info": session_info,
            "cards": cards,
            "candidates": list(candidates.values()),
            "setups": trade_setups,
            "report": report,
            "outcome_updates": outcome_updates,
            "health_stats": health_stats,
        }

    def _dispatch_telegram_report(
        self,
        report: Dict[str, str],
        outcome_updates: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send complete 3-section report + outcome update to Telegram with character chunking & rate limit handling."""
        logger.info("Dispatching Stage 2 Intelligence Report to Telegram...")
        sections = [
            ("Section 1: Daily Intelligence", report.get("section1", "")),
            ("Section 2: Swing Radar", report.get("section2", "")),
            ("Section 3: Actionable & Waiting Setups", report.get("section3", "")),
        ]
        if outcome_updates and outcome_updates.get("summary_text"):
            sections.append(("Active Positions & Outcome Tracker", outcome_updates["summary_text"]))

        for name, text in sections:
            if not text.strip():
                continue
            chunks = self._chunk_message(text, max_chars=4000)
            for chunk in chunks:
                try:
                    success = send_telegram(chunk, parse_mode="Markdown")
                    if success:
                        logger.info("Successfully sent %s chunk (%d chars) to Telegram", name, len(chunk))
                    else:
                        logger.warning("Telegram notification skipped or secrets not configured for %s", name)
                except Exception as e:
                    logger.error("Error sending %s to Telegram: %s", name, e)
                time.sleep(1.2)  # Throttling to prevent Telegram flood limits

    @staticmethod
    def _chunk_message(text: str, max_chars: int = 4000) -> List[str]:
        """Split a long markdown message into chunk sizes acceptable to Telegram (<= 4096 chars)."""
        if len(text) <= max_chars:
            return [text]
        lines = text.split("\n")
        chunks = []
        current = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > max_chars:
                if current:
                    chunks.append("\n".join(current))
                    current = [line]
                    current_len = len(line) + 1
                else:
                    chunks.append(line[:max_chars])
                    current = [line[max_chars:]]
                    current_len = len(line[max_chars:]) + 1
            else:
                current.append(line)
                current_len += len(line) + 1
        if current:
            chunks.append("\n".join(current))
        return chunks


def main():
    """CLI entry point for Stage 2 pipeline."""
    parser = argparse.ArgumentParser(description="Scheme Intel Stage 2: Daily Stock Intelligence Engine")
    parser.add_argument("--symbol", type=str, default=None, help="Specific stock symbol to evaluate")
    parser.add_argument("--date", type=str, default=None, help="Session date (YYYY-MM-DD)")
    parser.add_argument("--provider", type=str, default="mock", help="LLM Provider: mock, gemini, openai")
    parser.add_argument("--mode", type=str, default="production", choices=["production", "mock"], help="Execution mode: production (live Stage 1 sources) or mock")
    parser.add_argument("--dry-run", action="store_true", help="Run without persisting to database")
    parser.add_argument("--send", action="store_true", help="Send report to Telegram if credentials configured")
    parser.add_argument("--print-report", action="store_true", default=True, help="Print full Telegram report")
    parser.add_argument("--config", type=str, default=None, help="Path to watchlist.yaml")
    args = parser.parse_args()

    mode = "mock" if args.mode == "mock" else "production"
    provider = get_llm_provider(args.provider)
    pipeline = Stage2Pipeline(provider=provider, config_path=args.config, mode=mode)
    result = pipeline.run(target_symbol=args.symbol, session_date=args.date, dry_run=args.dry_run, send=args.send)

    if args.print_report:
        print("\n" + "=" * 60)
        print(result["report"]["full_text"])
        if result.get("outcome_updates") and result["outcome_updates"].get("summary_text"):
            print("\n" + result["outcome_updates"]["summary_text"])
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
