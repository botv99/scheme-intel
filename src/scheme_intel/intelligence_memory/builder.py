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
from ..intelligence.technical_score import TechnicalScoreEngine
from ..intelligence.fundamental_score import FundamentalIntelligenceEngine
from ..intelligence.market_sentiment import MarketSentimentEngine
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

    def build(
        self,
        stage2_result: Optional[Dict[str, Any]] = None,
        scheme_id: Optional[str] = None,
    ) -> IntelligenceSnapshot:
        """
        Construct a fresh IntelligenceSnapshot combining scheme metadata, setup intelligence,
        forward performance metrics, and Nifty 50 benchmark comparison.
        If scheme_id is provided, snapshot is strictly isolated to that scheme.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        snapshot_id = f"SNAP-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        # 1. Load targeted or active schemes from SchemeRegistry
        if scheme_id:
            target_scheme = SchemeRegistry.get(scheme_id)
            active_schemes = [target_scheme] if target_scheme else [SchemeRegistry.get_active()]
        else:
            active_schemes = SchemeRegistry.get_active_schemes()
            if not active_schemes:
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

        # 3. Initialize Technical and Fundamental scoring engines
        tech_engine = TechnicalScoreEngine()
        fund_engine = FundamentalIntelligenceEngine()

        benchmark_bars = []
        try:
            from ..db import SchemeIntelDB
            db_inst = SchemeIntelDB()
            conn = db_inst.connect()
            benchmark_bars = [dict(r) for r in conn.execute("SELECT * FROM benchmark_prices ORDER BY date ASC").fetchall()]
        except Exception as e:
            logger.debug("Could not load benchmark prices for technical scoring: %s", e)

        # 4. Build CompanyIntelligence for every stock across active schemes
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

                # Fallback: Query MarketDataEngine if technicals are not in candidate setup
                if price is None:
                    try:
                        from ..market.engine import MarketDataEngine
                        m_engine = MarketDataEngine()
                        m_snap, _, _ = m_engine.get_snapshot_with_status(sym)
                        if not m_snap and "IONEXCHANG" in sym:
                            m_snap, _, _ = m_engine.get_snapshot_with_status("ORGANICREC.BO")
                        if m_snap:
                            price = m_snap.close
                            change_pct = m_snap.day_change_pct
                            vol = m_snap.volume
                            avg_vol = m_snap.volume_20d_avg
                            support = m_snap.support
                            resistance = m_snap.resistance
                            rsi = m_snap.rsi14
                            trend = m_snap.trend_status
                    except Exception as e:
                        logger.debug("Market data fallback failed for %s: %s", sym, e)

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
                catalysts_list: List[str] = []
                if cand and cand.catalysts:
                    for cat in cand.catalysts:
                        c_str = f"{cat.catalyst_name} (Strength: {cat.strength})"
                        if cat.rationale:
                            c_str += f": {cat.rationale}"
                        catalysts_list.append(c_str)
                    cat0 = cand.catalysts[0]
                    catalyst_desc = f"{cat0.catalyst_name} (Strength: {cat0.strength})"
                    latest_dev = cat0.rationale or cat0.catalyst_name
                    key_devs.append(f"{stock.name}: {cat0.catalyst_name}")
                elif setup and setup.no_trade_reason:
                    latest_dev = setup.no_trade_reason

                if not catalysts_list and catalyst_desc:
                    catalysts_list.append(catalyst_desc)

                # Evidence from ingested news or setup
                evidence = ingested_news_by_symbol.get(sym, [])

                # Quantitative Technical & Fundamental Intelligence Scores
                tech_bars = []
                try:
                    from ..db import SchemeIntelDB
                    db_inst = SchemeIntelDB()
                    tech_bars = db_inst.get_historical_prices(sym, limit=120)
                    if not tech_bars and "." in sym:
                        tech_bars = db_inst.get_historical_prices(sym.split(".")[0], limit=120)
                    if not tech_bars and "IONEXCHANG" in sym:
                        tech_bars = db_inst.get_historical_prices("ORGANICREC.BO", limit=120)
                except Exception as e:
                    logger.debug("Could not load historical prices for %s: %s", sym, e)

                tech_res = tech_engine.calculate(tech_bars, benchmark_bars=benchmark_bars)
                fund_res = fund_engine.calculate(sym)

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
                    catalysts=catalysts_list,
                    fundamental_score=fund_res.score,
                    fundamental_intelligence_score=fund_res.score,
                    fundamental_score_components={k: v.to_dict() for k, v in fund_res.components.items()},
                    fundamental_score_version=fund_res.version,
                    fundamental_score_coverage=fund_res.coverage_pct,
                    fundamental_score_data_as_of=fund_res.data_as_of,
                    technical_intelligence_score=tech_res.score,
                    technical_score_components={k: v.to_dict() for k, v in tech_res.components.items()},
                    technical_score_version=tech_res.version,
                    technical_score_data_as_of=tech_res.data_as_of,
                    technical_score_coverage=tech_res.coverage_pct,
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

        # 5. Compute Market Sentiment and Cross-Layer Impacts (Stage 3)
        watchlist_cards_data = [comp.model_dump() for comp in companies_dict.values()]
        all_news_items = []
        for n_list in ingested_news_by_symbol.values():
            all_news_items.extend(n_list)

        all_catalysts = []
        for comp in companies_dict.values():
            for cat_str in comp.catalysts:
                all_catalysts.append({"catalyst": cat_str, "score": comp.score or 50})

        indian_sentiment = MarketSentimentEngine.calculate_indian_sentiment(
            benchmark_bars=benchmark_bars,
            watchlist_cards=watchlist_cards_data,
            news_items=all_news_items,
            catalysts=all_catalysts,
        )
        global_sentiment = MarketSentimentEngine.calculate_global_sentiment()

        scheme_impacts: Dict[str, Any] = {}
        for scheme in active_schemes:
            sec_list = [sec for st in scheme.watchlist for sec in st.sectors]
            scheme_impacts[scheme.id] = MarketSentimentEngine.evaluate_scheme_impact(
                scheme_id=scheme.id,
                scheme_name=scheme.name,
                indian_sentiment=indian_sentiment,
                global_sentiment=global_sentiment,
                scheme_sectors=sec_list,
            )

        watchlist_impacts: Dict[str, Any] = {}
        for sym, comp in companies_dict.items():
            if sym not in watchlist_impacts:
                watchlist_impacts[sym] = MarketSentimentEngine.evaluate_watchlist_impact(
                    stock_symbol=sym,
                    short_symbol=comp.short_symbol,
                    company_name=comp.name,
                    indian_sentiment=indian_sentiment,
                    global_sentiment=global_sentiment,
                    catalysts=comp.catalysts,
                    technical_trend=comp.trend,
                )

        market_and_global_sentiment = {
            "section_title": "MARKET & GLOBAL SENTIMENT",
            "indian_market": {
                "classification": indian_sentiment.classification.value,
                "score": indian_sentiment.score,
                "confidence": indian_sentiment.confidence,
                "key_drivers": [indian_sentiment.nifty_direction] if indian_sentiment.nifty_direction else [],
                "evidence": [e.get("source", "") for e in indian_sentiment.evidence],
                "breadth": indian_sentiment.breadth,
                "sector_rotation": indian_sentiment.sector_rotation,
            },
            "global_market": {
                "classification": global_sentiment.classification.value,
                "score": global_sentiment.score,
                "confidence": global_sentiment.confidence,
                "key_drivers": global_sentiment.key_drivers,
                "evidence": global_sentiment.evidence,
                "risk_regime": global_sentiment.risk_regime.value,
            },
            "scheme_impact": {
                sid: {
                    "scheme_name": imp.scheme_name,
                    "scheme_level_implications": imp.estimated_directional_impact.value,
                    "positive_factors": imp.positive_factors,
                    "negative_factors": imp.negative_factors,
                    "uncertainties": imp.neutral_uncertain_factors,
                    "confidence": imp.confidence,
                }
                for sid, imp in scheme_impacts.items()
            },
            "watchlist_impact": {
                sym: {
                    "relevant_stock": imp.stock,
                    "sector_effect": imp.sector_impact.value,
                    "scheme_effect": imp.scheme_relationship,
                    "global_effect": imp.global_market_impact.value,
                    "company_specific_interaction": imp.company_catalyst_interaction,
                    "confidence": imp.confidence,
                    "estimated_impact": imp.estimated_impact,
                }
                for sym, imp in watchlist_impacts.items()
            },
        }

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
            indian_sentiment=indian_sentiment,
            global_sentiment=global_sentiment,
            scheme_impacts=scheme_impacts,
            watchlist_impacts=watchlist_impacts,
            market_and_global_sentiment=market_and_global_sentiment,
        )
        return snapshot

    def build_and_save(
        self,
        stage2_result: Optional[Dict[str, Any]] = None,
        scheme_id: Optional[str] = None,
        also_save_to_root: bool = False,
    ) -> Path:
        """Build snapshot and atomically persist to disk under scheme namespace."""
        snapshot = self.build(stage2_result=stage2_result, scheme_id=scheme_id)
        if scheme_id:
            store = IntelligenceStore.get_store_for_scheme(scheme_id)
            root_compat = also_save_to_root or (scheme_id.lower() == "gobardhan")
            return store.save(snapshot, also_save_to_root=root_compat)
        return self.store.save(snapshot, also_save_to_root=True)

    def build_all_schemes(self, stage2_result: Optional[Dict[str, Any]] = None) -> Dict[str, Path]:
        """Build and save isolated snapshots for all registered enabled schemes."""
        saved_paths: Dict[str, Path] = {}
        for scheme in SchemeRegistry.get_active_schemes():
            saved_paths[scheme.id] = self.build_and_save(
                stage2_result=stage2_result,
                scheme_id=scheme.id,
                also_save_to_root=(scheme.id.lower() == "gobardhan"),
            )
        return saved_paths
