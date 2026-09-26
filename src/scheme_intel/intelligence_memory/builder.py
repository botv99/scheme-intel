"""
Intelligence Snapshot Builder.
Extracts structured intelligence from Stage 2 database, Performance Analytics,
SchemeRegistry, and latest ingestion artifacts to construct an IntelligenceSnapshot.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from .models import (
    IntelligenceSnapshot,
    CompanyIntelligence,
    SchemeIntelligence,
    PerformanceIntelligence,
    BenchmarkIntelligence,
)
from .store import IntelligenceStore, DEFAULT_SNAPSHOT_PATH
from ..schemes.registry import SchemeRegistry
from ..schemes.models import SchemeConfig, SchemeStock
from ..stage2.storage import Stage2Database, DEFAULT_STAGE2_DB_PATH
from ..stage2.models import TradeSetup
from ..logger import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


class IntelligenceSnapshotBuilder:
    """Builds precalculated, validated IntelligenceSnapshots after the daily pipeline."""

    def __init__(
        self,
        db: Optional[Stage2Database] = None,
        store: Optional[IntelligenceStore] = None,
    ):
        self.db = db or Stage2Database()
        self.store = store or IntelligenceStore()

    def build(self, stage2_result: Optional[Dict[str, Any]] = None) -> IntelligenceSnapshot:
        """
        Construct a fresh IntelligenceSnapshot combining scheme metadata, setup intelligence,
        forward performance metrics, and Nifty 50 benchmark comparison.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        snapshot_id = f"SNAP-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        # 1. Load active schemes from SchemeRegistry
        active_schemes = SchemeRegistry.get_active_schemes()
        if not active_schemes:
            # Fallback to default GOBARdhan if registry is empty
            active_schemes = [SchemeRegistry.get_active()]

        scheme_ids = [s.id for s in active_schemes]
        schemes_dict: Dict[str, SchemeIntelligence] = {}
        companies_dict: Dict[str, CompanyIntelligence] = {}
        qualified_setups: List[str] = []
        waiting_setups: List[str] = []

        # 2. Extract latest setups from memory or database
        latest_setups_by_symbol: Dict[str, TradeSetup] = {}
        if stage2_result and "setups" in stage2_result:
            for s in stage2_result["setups"]:
                latest_setups_by_symbol[s.stock.symbol.upper()] = s
        else:
            db_setups = self.db.list_setups()
            # Group by symbol, keeping the latest one
            for s in db_setups:
                sym_upper = s.stock.symbol.upper()
                if sym_upper not in latest_setups_by_symbol:
                    latest_setups_by_symbol[sym_upper] = s

        # Also load latest ingested news for evidence if available
        ingested_news_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        ingested_path = REPO_ROOT / "data" / "ingested.json"
        if ingested_path.exists():
            try:
                ingested_data = json.loads(ingested_path.read_text(encoding="utf-8"))
                for item in ingested_data.get("news", []):
                    comp_title = item.get("title", "")
                    for sym, setup in latest_setups_by_symbol.items():
                        c_name = setup.stock.name.lower()
                        short_sym = sym.split(".")[0].lower()
                        if c_name in comp_title.lower() or short_sym in comp_title.lower():
                            ingested_news_by_symbol.setdefault(sym, []).append({
                                "source": item.get("source", "News"),
                                "title": item.get("title", ""),
                                "url": item.get("url", ""),
                                "date": item.get("published_at", "")[:10] if item.get("published_at") else "",
                            })
            except Exception as e:
                logger.debug("Could not read ingested.json for snapshot evidence: %s", e)

        # 3. Build CompanyIntelligence for every stock across active schemes
        for scheme in active_schemes:
            qualified_count = 0
            wait_count = 0
            no_trade_count = 0
            data_unavail_count = 0
            key_devs: List[str] = []

            for stock in scheme.watchlist:
                sym = stock.symbol.upper()
                short_sym = sym.split(".")[0].upper()
                setup = latest_setups_by_symbol.get(sym) or latest_setups_by_symbol.get(short_sym)

                # Determine metrics from setup or defaults
                status = setup.status if setup else "NO_TRADE"
                if status == "QUALIFIED_SETUP":
                    qualified_count += 1
                    qualified_setups.append(sym)
                elif status == "WAIT":
                    wait_count += 1
                    waiting_setups.append(sym)
                elif status in ("DATA_UNAVAILABLE", "DATA_STALE", "DATA_INSUFFICIENT"):
                    data_unavail_count += 1
                else:
                    no_trade_count += 1

                # Extract technical & setup details
                cand = setup.candidate if setup else None
                tech = cand.technicals if cand else None
                bull = setup.bull_thesis if setup else None
                bear = setup.bear_thesis if setup else None
                risk = setup.risk if setup else None
                wait = setup.wait_conditions if setup else None

                price = tech.close if tech else None
                change_pct = tech.day_change_pct if tech else None
                vol = tech.volume if tech else None
                avg_vol = tech.volume_20d_avg if tech else None
                support = tech.support if tech else None
                resistance = tech.resistance if tech else None
                rsi = tech.rsi14 if tech else None
                trend = tech.trend_status if tech else None

                archetype = cand.archetype if cand else None
                score = cand.score if cand else None
                trigger_price = wait.trigger_price if wait and wait.trigger_price else (risk.ideal_entry if risk else None)
                stop_loss = wait.invalidation_level if wait and wait.invalidation_level else (risk.stop_loss if risk else None)
                target = risk.target_1 if risk else None

                bull_thesis = bull.core_thesis if bull else None
                bear_thesis = bear.core_thesis if bear else None
                if risk:
                    if not risk.passed:
                        risk_summary = f"Vetoed: {risk.veto_reason}"
                    else:
                        risk_summary = f"R:R {risk.risk_reward_ratio:.1f}:1 | Max Risk {risk.actual_risk_pct}% | Target {risk.target_1}"
                else:
                    risk_summary = None

                waiting_conds = wait.exact_confirmation_required if wait and wait.exact_confirmation_required else ([wait.why_not_ready] if wait and wait.why_not_ready else [])
                ai_provider = setup.ai_provider if setup else None
                next_session = setup.next_trading_session if setup else None

                # Extract latest development / catalyst
                latest_dev = None
                catalyst_desc = None
                if cand and cand.catalysts:
                    cat0 = cand.catalysts[0]
                    catalyst_desc = f"{cat0.catalyst_name} (Strength: {cat0.strength})"
                    latest_dev = cat0.rationale or cat0.catalyst_name
                    key_devs.append(f"{stock.name}: {cat0.catalyst_name}")
                elif setup and setup.no_trade_reason:
                    latest_dev = setup.no_trade_reason

                # Evidence from ingested news or setup
                evidence = ingested_news_by_symbol.get(sym, [])

                company_intel = CompanyIntelligence(
                    symbol=sym,
                    short_symbol=short_sym,
                    name=stock.name,
                    scheme_id=scheme.id,
                    scheme_name=scheme.name,
                    relevance="High",
                    mapping_rationale=stock.rationale,
                    latest_development=latest_dev,
                    catalyst=catalyst_desc,
                    price=price,
                    change_pct=change_pct,
                    volume=vol,
                    avg_volume=avg_vol,
                    trend=trend,
                    support=support,
                    resistance=resistance,
                    rsi=rsi,
                    status=status,
                    archetype=archetype,
                    score=score,
                    trigger_price=trigger_price,
                    stop_loss=stop_loss,
                    target=target,
                    bull_thesis=bull_thesis,
                    bear_thesis=bear_thesis,
                    risk_summary=risk_summary,
                    waiting_conditions=waiting_conds,
                    next_session=next_session,
                    ai_provider=ai_provider,
                    evidence=evidence,
                    updated_at=setup.created_at if setup else now_utc,
                )
                companies_dict[sym] = company_intel
                companies_dict[short_sym] = company_intel

            # Scheme overview
            schemes_dict[scheme.id] = SchemeIntelligence(
                scheme_id=scheme.id,
                name=scheme.name,
                description=scheme.description,
                watchlist_count=len(scheme.watchlist),
                qualified_setups_count=qualified_count,
                waiting_count=wait_count,
                no_trade_count=no_trade_count,
                data_unavailable_count=data_unavail_count,
                key_developments=key_devs[:5],
                important_sources=[s.name for s in scheme.sources[:4]],
                last_update=now_utc,
            )

        # 4. Load or compute performance & benchmark intelligence
        perf_intel = PerformanceIntelligence()
        bench_intel = BenchmarkIntelligence()
        perf_path = REPO_ROOT / "data" / "performance" / "latest.json"
        if perf_path.exists():
            try:
                perf_data = json.loads(perf_path.read_text(encoding="utf-8"))
                ov = perf_data.get("overview", {})
                bc = perf_data.get("benchmark_comparison", {})
                di = perf_data.get("data_integrity", {})

                perf_intel = PerformanceIntelligence(
                    completed_trades=ov.get("completed_trades", 0),
                    validation_threshold=30,
                    validation_status=ov.get("validation_status", "INSUFFICIENT_SAMPLE"),
                    win_rate=ov.get("win_rate"),
                    avg_pnl=ov.get("average_pnl"),
                    profit_factor=ov.get("profit_factor"),
                    expectancy=ov.get("expectancy"),
                    summary_text=ov.get("validation_summary", ""),
                    audit_status=di.get("status", "PASS"),
                )

                bench_intel = BenchmarkIntelligence(
                    status=bc.get("status", "UNAVAILABLE — 0 completed trades"),
                    benchmark_id=bc.get("benchmark_id", "NIFTY50"),
                    completed_trades=bc.get("completed_trades", 0),
                    trades_evaluated=bc.get("trades_evaluated", 0),
                    strategy_return=bc.get("average_strategy_return"),
                    benchmark_return=bc.get("average_benchmark_return"),
                    excess_return=bc.get("average_excess_return"),
                    win_rate_vs_benchmark_pct=bc.get("win_rate_vs_benchmark_pct"),
                    trade_comparisons=bc.get("trade_comparisons", []),
                    reason=bc.get("reason"),
                )
            except Exception as e:
                logger.warning("Failed parsing performance latest.json: %s", e)

        session_info = stage2_result.get("session_info") if stage2_result else None
        pipeline_run_id = getattr(session_info, "analysis_date", None) or (session_info.get("analysis_date") if isinstance(session_info, dict) else None)

        snapshot = IntelligenceSnapshot(
            snapshot_id=snapshot_id,
            generated_at=now_utc,
            pipeline_run_id=pipeline_run_id,
            scheme_ids=scheme_ids,
            schemes=schemes_dict,
            companies=companies_dict,
            qualified_setups=qualified_setups,
            waiting_setups=waiting_setups,
            performance=perf_intel,
            benchmark=bench_intel,
        )
        return snapshot

    def build_and_save(self, stage2_result: Optional[Dict[str, Any]] = None) -> Path:
        """Build snapshot and atomically persist to disk."""
        snapshot = self.build(stage2_result=stage2_result)
        return self.store.save(snapshot)
