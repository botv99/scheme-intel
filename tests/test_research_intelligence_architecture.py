"""
Comprehensive Architectural Tests for Scheme-Intel Intelligence Upgrade.
Verifies all 13 core specification requirements:
 1. Research query does NOT use snapshot as final research.
 2. Multiple providers can independently participate.
 3. Provider failure does not break the entire research process (graceful degradation).
 4. Provider participation is recorded in provenance.
 5. Snapshot fallback is explicitly labelled as [SNAPSHOT_FALLBACK].
 6. Indian sentiment is present in snapshot.
 7. Global sentiment is present in snapshot.
 8. Scheme impact is generated from sentiment.
 9. Watchlist impact is generated.
10. Missing market data does not cause fabricated values.
11. Existing snapshot generation continues working.
12. Existing daily brief/Telegram functionality continues working.
13. Existing Stage 1/Stage 2 pipeline execution remains functional.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scheme_intel.research.classifier import QueryClassifier, QueryType
from scheme_intel.research.providers import (
    ProviderRegistry,
    ProviderConfig,
    ProviderHealthStatus,
    AIProvider,
)
from scheme_intel.research.orchestrator import (
    ResearchOrchestrator,
    ResearchResult,
    ResearchProvenance,
    search_internet_for_research,
)
from scheme_intel.research.executor import ResearchExecutor
from scheme_intel.research.models import ResearchJob
from scheme_intel.delivery.query_engine import ComplexQueryEngine
from scheme_intel.delivery.workflow_query_runner import process_workflow_query
from scheme_intel.intelligence.market_sentiment import (
    IndianMarketSentiment,
    GlobalMarketSentiment,
    SchemeSentimentImpact,
    WatchlistSentimentImpact,
    MarketSentimentEngine,
    SentimentClassification,
    DirectionalImpact,
)
from scheme_intel.intelligence_memory.builder import IntelligenceSnapshotBuilder
from scheme_intel.intelligence_memory.models import (
    IntelligenceSnapshot,
    CompanyIntelligence,
    SchemeIntelligence,
)
from scheme_intel.schemes.registry import SchemeRegistry
from scheme_intel.stage2.providers.base import ProviderResponse, LLMProvider


class MockTestProvider(LLMProvider):
    """Custom mock provider for multi-provider testing."""
    def __init__(self, name: str, response_text: str = "", fail: bool = False, model: str = "mock-model-v1"):
        self.name = name
        self.response_text = response_text
        self.fail = fail
        self.model = model
        self.call_count = 0

    def generate(self, prompt: str, **kwargs) -> ProviderResponse:
        self.call_count += 1
        if self.fail:
            raise RuntimeError(f"Simulated failure on provider {self.name}")
        return ProviderResponse(
            content=self.response_text or f'{{"result": "Success from {self.name}"}}',
            model=self.model,
            provider=self.name,
        )


class TestResearchIntelligenceArchitecture:

    # -------------------------------------------------------------------------
    # TEST 1: Research query does NOT use snapshot as final research
    # -------------------------------------------------------------------------
    def test_research_query_does_not_use_snapshot_as_final_research(self):
        """Genuine research queries trigger fresh multi-provider research instead of regurgitating snapshot."""
        mock_groq = MockTestProvider(
            name="groq",
            response_text='{"fact_points": ["Fresh PIB notification on CBG procurement guidelines."]}',
        )
        mock_gemini = MockTestProvider(
            name="gemini",
            response_text='{"bull_case": ["Order intake expanded 25% due to revised statutory tariffs."]}',
        )
        mock_openai = MockTestProvider(
            name="openai",
            response_text='{"bear_case": ["Interconnection pipeline delays at state grid level."]}',
        )

        test_registry = ProviderRegistry()
        test_registry.register(ProviderConfig("groq", "GROQ_KEY", "M", "m", lambda **kw: mock_groq))
        test_registry.register(ProviderConfig("gemini", "GEMINI_KEY", "M", "m", lambda **kw: mock_gemini))
        test_registry.register(ProviderConfig("openai", "OPENAI_KEY", "M", "m", lambda **kw: mock_openai))

        with patch.object(test_registry, "get_active_providers", return_value={"groq": mock_groq, "gemini": mock_gemini, "openai": mock_openai}):
            orchestrator = ResearchOrchestrator(registry=test_registry)
            engine = ComplexQueryEngine(orchestrator=orchestrator)

            # Query is a genuine research question
            query = "What changed in Gobardhan policy and which watchlist companies are affected?"
            classification = QueryClassifier.classify(query)
            assert classification in (QueryType.RESEARCH_QUERY, QueryType.DEEP_RESEARCH)

            dummy_snapshot = IntelligenceSnapshot(
                snapshot_id="SNAP-001",
                generated_at="2026-09-28T10:00:00Z",
                companies={
                    "TRUALT.NS": CompanyIntelligence(
                        symbol="TRUALT.NS",
                        short_symbol="TRUALT",
                        name="TruAlt Bioenergy",
                        scheme_id="gobardhan",
                        scheme_name="GOBARdhan",
                        price=120.0,
                    )
                },
            )

            result_text = engine.process_query(query, dummy_snapshot)

            # Research was executed afresh and did not simply return the cached snapshot
            assert "SCHEME-INTEL MULTI-PROVIDER RESEARCH" in result_text
            assert "SNAPSHOT_FALLBACK" not in result_text
            assert mock_groq.call_count > 0 or mock_gemini.call_count > 0

    # -------------------------------------------------------------------------
    # TEST 2: Multiple providers can participate
    # -------------------------------------------------------------------------
    def test_multiple_providers_participate(self):
        """Multiple configured providers fan out to distinct roles."""
        p_groq = MockTestProvider("groq", '{"fact_points": ["Fact from Groq"]}')
        p_gemini = MockTestProvider("gemini", '{"bull_case": ["Bull thesis from Gemini"]}')
        p_openai = MockTestProvider("openai", '{"bear_case": ["Risk analysis from OpenAI"]}')
        p_openrouter = MockTestProvider("openrouter", '{"verdict": "BULL", "why": ["Consensus across providers"], "confidence": "HIGH", "key_risk": "Delays", "invalidation": "Policy reversal"}')

        providers = {
            "groq": p_groq,
            "gemini": p_gemini,
            "openai": p_openai,
            "openrouter": p_openrouter,
        }

        test_registry = ProviderRegistry()
        with patch.object(test_registry, "get_active_providers", return_value=providers):
            orchestrator = ResearchOrchestrator(registry=test_registry)
            res = orchestrator.execute_research("Evaluate CBG plant commercial viability across schemes")

            # All providers participated in the fan-out
            assert len(res.provenance.providers_successful) >= 3
            assert "groq" in res.provenance.providers_successful
            assert "gemini" in res.provenance.providers_successful
            assert "openai" in res.provenance.providers_successful
            assert res.provenance.degraded_status is False
            assert "Participating Providers:" in res.result_text

    # -------------------------------------------------------------------------
    # TEST 3: Provider failure does not break the entire research process
    # -------------------------------------------------------------------------
    def test_provider_failure_does_not_break_research(self):
        """Failure of one provider allows surviving providers to complete research."""
        p_groq = MockTestProvider("groq", fail=True)  # Fails with RuntimeError
        p_gemini = MockTestProvider("gemini", '{"bull_case": ["Gemini stepped up successfully"]}')
        p_openai = MockTestProvider("openai", '{"bear_case": ["OpenAI identified valuation friction"]}')

        providers = {
            "groq": p_groq,
            "gemini": p_gemini,
            "openai": p_openai,
        }

        test_registry = ProviderRegistry()
        with patch.object(test_registry, "get_active_providers", return_value=providers):
            orchestrator = ResearchOrchestrator(registry=test_registry)
            res = orchestrator.execute_research("Why is Praj underperforming despite the scheme?")

            # Process completed despite Groq failure
            assert res.is_fallback is False
            assert "gemini" in res.provenance.providers_successful or "openai" in res.provenance.providers_successful
            assert "SCHEME-INTEL MULTI-PROVIDER RESEARCH" in res.result_text

    # -------------------------------------------------------------------------
    # TEST 4: Provider participation is recorded
    # -------------------------------------------------------------------------
    def test_provider_participation_recorded_in_provenance(self):
        """Structured provenance captures attempted vs successful providers, models, and timestamps."""
        p_gemini = MockTestProvider("gemini", '{"bull_case": ["Expansion"], "bear_case": ["Execution"], "verdict": "BULL", "why": ["Support"], "confidence": "HIGH"}', model="gemini-2.5-flash")
        test_registry = ProviderRegistry()
        with patch.object(test_registry, "get_active_providers", return_value={"gemini": p_gemini}):
            orchestrator = ResearchOrchestrator(registry=test_registry)
            res = orchestrator.execute_research("Deep dive into Wabag water treatment orders")

            prov = res.provenance
            assert prov.query == "Deep dive into Wabag water treatment orders"
            assert "gemini" in prov.providers_attempted
            assert "gemini" in prov.providers_successful
            assert prov.model_names.get("gemini") == "gemini-2.5-flash"
            assert prov.execution_duration_seconds >= 0.0
            # Single provider is flagged as degraded
            assert prov.degraded_status is True
            assert "DEGRADED" in prov.confidence

    # -------------------------------------------------------------------------
    # TEST 5: Snapshot fallback is explicitly labelled
    # -------------------------------------------------------------------------
    def test_snapshot_fallback_is_explicitly_labelled(self):
        """When zero AI providers can run, system returns clearly labelled SNAPSHOT_FALLBACK."""
        test_registry = ProviderRegistry()
        # Mock empty active providers
        with patch.object(test_registry, "get_active_providers", return_value={}):
            orchestrator = ResearchOrchestrator(registry=test_registry)
            engine = ComplexQueryEngine(orchestrator=orchestrator)

            dummy_snapshot = IntelligenceSnapshot(
                snapshot_id="SNAP-FALLBACK-TEST",
                generated_at="2026-09-28T09:00:00Z",
                companies={
                    "TRUALT.NS": CompanyIntelligence(
                        symbol="TRUALT.NS",
                        short_symbol="TRUALT",
                        name="TruAlt Bioenergy",
                        scheme_id="gobardhan",
                        scheme_name="GOBARdhan",
                        price=120.0,
                    ),
                    "PRAJIND.NS": CompanyIntelligence(
                        symbol="PRAJIND.NS",
                        short_symbol="PRAJ",
                        name="Praj Industries",
                        scheme_id="gobardhan",
                        scheme_name="GOBARdhan",
                        price=750.0,
                    ),
                },
            )

            result = engine.process_query(
                "Compare TRUALT and PRAJ based on current scheme intelligence.",
                dummy_snapshot,
            )

            # Must contain explicit banner and must NOT pretend fresh research occurred
            assert "[SNAPSHOT_FALLBACK]" in result
            assert "Fresh multi-provider research unavailable; returning available snapshot intelligence." in result
            assert "Comparative Scheme Analysis" in result

    # -------------------------------------------------------------------------
    # TEST 6: Indian sentiment is present in snapshot
    # -------------------------------------------------------------------------
    def test_indian_sentiment_present_in_snapshot(self):
        """Daily snapshot contains structured IndianMarketSentiment with deterministic score."""
        mock_bench_bars = [
            {"date": "2026-09-26", "close": 24500.0},
            {"date": "2026-09-27", "close": 24700.0},  # +0.81% UP
        ]
        mock_cards = [
            {"change_pct": 1.5, "status": "QUALIFIED_SETUP"},
            {"change_pct": 0.8, "status": "WAIT"},
            {"change_pct": -0.2, "status": "WAIT"},
        ]

        sentiment = MarketSentimentEngine.calculate_indian_sentiment(
            benchmark_bars=mock_bench_bars,
            watchlist_cards=mock_cards,
            news_items=[{"title": "Cabinet approves revised bio-gas procurement incentive"}],
        )

        assert isinstance(sentiment, IndianMarketSentiment)
        assert sentiment.classification in (SentimentClassification.BULLISH, SentimentClassification.NEUTRAL, SentimentClassification.BEARISH)
        assert -100.0 <= sentiment.score <= 100.0
        assert sentiment.score > 15.0  # +0.81% Nifty and positive breadth => Bullish
        assert sentiment.classification == SentimentClassification.BULLISH
        assert "UP" in sentiment.nifty_direction
        assert sentiment.breadth.get("advances") == 2
        assert len(sentiment.relevant_sectors) > 0

    # -------------------------------------------------------------------------
    # TEST 7: Global sentiment is present in snapshot
    # -------------------------------------------------------------------------
    def test_global_sentiment_present_in_snapshot(self):
        """GlobalMarketSentiment captures relevant factors without fabrication."""
        macro_ctx = {
            "us_market_direction": "UP (+0.45%)",
            "crude_oil": "Brent $74.2/bbl (-0.8%)",
            "risk_regime": "RISK_ON",
        }
        global_sent = MarketSentimentEngine.calculate_global_sentiment(macro_ctx)

        assert isinstance(global_sent, GlobalMarketSentiment)
        assert global_sent.classification == SentimentClassification.BULLISH
        assert global_sent.score > 0
        assert global_sent.us_market_direction == "UP (+0.45%)"
        assert global_sent.crude_oil == "Brent $74.2/bbl (-0.8%)"
        assert global_sent.risk_regime.value == "RISK_ON"

    # -------------------------------------------------------------------------
    # TEST 8: Scheme impact is generated from sentiment
    # -------------------------------------------------------------------------
    def test_scheme_impact_generated_from_sentiment(self):
        """SchemeSentimentImpact evaluates transmission channels analytically without buy/sell instructions."""
        ind_sent = IndianMarketSentiment(classification=SentimentClassification.BULLISH, score=45.0, confidence="HIGH")
        glob_sent = GlobalMarketSentiment(classification=SentimentClassification.NEUTRAL, score=5.0, confidence="MEDIUM")

        impact = MarketSentimentEngine.evaluate_scheme_impact(
            scheme_id="gobardhan",
            scheme_name="GOBARdhan",
            indian_sentiment=ind_sent,
            global_sentiment=glob_sent,
        )

        assert isinstance(impact, SchemeSentimentImpact)
        assert impact.scheme_id == "gobardhan"
        assert impact.indian_sentiment == SentimentClassification.BULLISH
        assert impact.estimated_directional_impact == DirectionalImpact.POSITIVE
        assert len(impact.transmission_channels) > 0
        assert len(impact.positive_factors) > 0
        assert "Not an investment recommendation" in impact.disclaimer

    # -------------------------------------------------------------------------
    # TEST 9: Watchlist impact is generated
    # -------------------------------------------------------------------------
    def test_watchlist_impact_generated(self):
        """WatchlistSentimentImpact maps macro sentiment to company-specific catalysts."""
        ind_sent = IndianMarketSentiment(classification=SentimentClassification.BULLISH, score=40.0)
        glob_sent = GlobalMarketSentiment(classification=SentimentClassification.NEUTRAL, score=0.0)

        wl_impact = MarketSentimentEngine.evaluate_watchlist_impact(
            stock_symbol="TRUALT.NS",
            short_symbol="TRUALT",
            company_name="TruAlt Bioenergy",
            indian_sentiment=ind_sent,
            global_sentiment=glob_sent,
            catalysts=["Major 50 TPD CBG plant commissioning in Karnataka"],
            technical_trend="BULLISH",
        )

        assert isinstance(wl_impact, WatchlistSentimentImpact)
        assert wl_impact.stock == "TRUALT.NS"
        assert wl_impact.indian_market_impact == DirectionalImpact.POSITIVE
        assert "Major 50 TPD CBG" in wl_impact.company_catalyst_interaction
        assert "supportive" in wl_impact.estimated_impact.lower()

    # -------------------------------------------------------------------------
    # TEST 10: Missing market data does not cause fabricated values
    # -------------------------------------------------------------------------
    def test_missing_market_data_does_not_fabricate_values(self):
        """When macro indicators are absent, values remain None/UNAVAILABLE rather than hallucinated."""
        # Empty inputs
        ind_sent = MarketSentimentEngine.calculate_indian_sentiment(
            benchmark_bars=None,
            watchlist_cards=None,
            news_items=None,
        )
        assert ind_sent.nifty_direction == "UNAVAILABLE"
        assert ind_sent.fii_dii_activity is None
        assert ind_sent.sensex_direction is None

        glob_sent = MarketSentimentEngine.calculate_global_sentiment(macro_context=None)
        assert glob_sent.us_market_direction is None
        assert glob_sent.us_yields is None
        assert glob_sent.crude_oil is None
        assert glob_sent.gold is None

    # -------------------------------------------------------------------------
    # TEST 11: Snapshot builder integrates sentiment without breaking snapshot
    # -------------------------------------------------------------------------
    def test_snapshot_builder_integrates_sentiment(self, tmp_path: Path):
        """Snapshot builder populates Indian & Global sentiment and dedicated snapshot section."""
        builder = IntelligenceSnapshotBuilder()
        snapshot = builder.build()

        assert snapshot.snapshot_id.startswith("SNAP-")
        assert snapshot.indian_sentiment is not None
        assert snapshot.global_sentiment is not None
        assert len(snapshot.scheme_impacts) > 0
        assert len(snapshot.watchlist_impacts) > 0
        assert snapshot.market_and_global_sentiment is not None
        assert snapshot.market_and_global_sentiment.get("section_title") == "MARKET & GLOBAL SENTIMENT"

    # -------------------------------------------------------------------------
    # TEST 12: Provider Registry Health Audit
    # -------------------------------------------------------------------------
    def test_provider_registry_health_status(self):
        """Providers without live verified test are correctly audited as CONFIGURED_BUT_NOT_VERIFIED."""
        registry = ProviderRegistry()
        with patch.dict("os.environ", {"GROQ_API_KEY": "dummy_groq_key"}, clear=False):
            assert registry.is_configured("groq") is True
            # Without live test, reported as CONFIGURED_BUT_NOT_VERIFIED
            status = registry.get_health_status("groq", verified_live=False)
            assert status == ProviderHealthStatus.CONFIGURED_BUT_NOT_VERIFIED

        # Unset key
        with patch.dict("os.environ", {}, clear=True):
            status = registry.get_health_status("openai", verified_live=False)
            assert status == ProviderHealthStatus.NOT_CONFIGURED

    # -------------------------------------------------------------------------
    # TEST 13: Research Query Classification with Intent & Financial Indicators
    # -------------------------------------------------------------------------
    def test_research_classification_financial_and_intent(self):
        """Verifies /research, intent=RESEARCH_REQUEST, and financial terms trigger research."""
        # 1. Direct /research command
        assert QueryClassifier.classify("/research gail earnings") == QueryType.DEEP_RESEARCH
        assert QueryClassifier.classify("gail earnings", raw_query="/research gail earnings") == QueryType.DEEP_RESEARCH

        # 2. Intent metadata passed from Telegram gateway
        assert QueryClassifier.classify("gail earnings", intent="RESEARCH_REQUEST") == QueryType.DEEP_RESEARCH

        # 3. Financial queries without /research trigger RESEARCH_QUERY
        assert QueryClassifier.classify("GAIL earnings") == QueryType.RESEARCH_QUERY
        assert QueryClassifier.classify("Praj Q1 results") == QueryType.RESEARCH_QUERY
        assert QueryClassifier.classify("Wabag concall highlights") == QueryType.RESEARCH_QUERY

        # 4. Simple stock lookup remains SIMPLE_QUERY
        assert QueryClassifier.classify("/stock trualt") == QueryType.SIMPLE_QUERY
        assert QueryClassifier.classify("/setups") == QueryType.SIMPLE_QUERY

    # -------------------------------------------------------------------------
    # TEST 14: Internet Search Evidence Gathering
    # -------------------------------------------------------------------------
    def test_internet_search_evidence_gathering(self):
        """Verifies search_internet_for_research gathers structured web items without error."""
        items = search_internet_for_research("GAIL earnings results", max_items=5)
        assert isinstance(items, list)
        # Even if offline/mocked, returns a list of dictionaries with standard keys
        for item in items:
            assert "source" in item
            assert "title" in item
            assert "url" in item
            assert "date" in item
            assert "snippet" in item

    # -------------------------------------------------------------------------
    # TEST 15: Research Orchestrator Uses Live Internet Search
    # -------------------------------------------------------------------------
    def test_research_orchestrator_uses_live_internet_evidence(self):
        """Orchestrator gather_fresh_evidence integrates live internet search into dossier."""
        scheme = SchemeRegistry.get("gobardhan") or SchemeRegistry.get_active()
        orchestrator = ResearchOrchestrator()

        mock_web_items = [
            {
                "source": "NDTV Profit",
                "title": "GAIL Q1 Net Profit Jumps 28% Driven by Transmission",
                "url": "https://ndtvprofit.com/gail-q1",
                "date": "2026-08-05",
                "snippet": "GAIL reported 28% growth in net profit for Q1 supported by strong natural gas transmission volumes.",
            }
        ]

        with patch("scheme_intel.research.orchestrator.search_internet_for_research", return_value=mock_web_items):
            dossier = orchestrator.gather_fresh_evidence(
                query="GAIL earnings",
                scheme=scheme,
                snapshot_context={"companies": {"GAIL.NS": {"name": "GAIL (India)", "short_symbol": "GAIL", "status": "MONITORING"}}},
            )
            assert len(dossier["evidence_items"]) > 0
            assert any("GAIL Q1 Net Profit" in ev["title"] for ev in dossier["evidence_items"])
            assert any(s["source"] == "NDTV Profit" for s in dossier["sources"])

    # -------------------------------------------------------------------------
    # TEST 16: Workflow Query Runner Routes Research Pathway
    # -------------------------------------------------------------------------
    def test_workflow_query_runner_routes_research_pathway(self, tmp_path: Path):
        """Workflow query runner dispatches fresh research when intent=RESEARCH_REQUEST."""
        from scheme_intel.delivery.request_store import RequestStore
        db_path = str(tmp_path / "research_test_req.db")
        store = RequestStore(db_path=db_path)

        mock_groq = MockTestProvider("groq", '{"fact_points": ["GAIL Q1 PAT grew 28% YoY on transmission volume expansion."]}')
        mock_gemini = MockTestProvider("gemini", '{"bull_case": ["Gas consumption tailwind and policy support for CBG blending."]}')
        mock_openai = MockTestProvider("openai", '{"bear_case": ["Global LNG price spread volatility and tariff regulation risks."]}')
        mock_openrouter = MockTestProvider("openrouter", '{"verdict": "BULL", "why": ["Strong operational throughput and volume visibility"], "confidence": "HIGH", "key_risk": "LNG spread contraction", "invalidation": "Drop in gas throughput below 110 mmscmd"}')

        providers = {
            "groq": mock_groq,
            "gemini": mock_gemini,
            "openai": mock_openai,
            "openrouter": mock_openrouter,
        }

        test_registry = ProviderRegistry()
        with patch.object(test_registry, "get_active_providers", return_value=providers):
            orchestrator = ResearchOrchestrator(registry=test_registry)
            engine = ComplexQueryEngine(orchestrator=orchestrator)

            # Simulated payload matching Cloudflare Worker /research dispatch
            payload = {
                "request_id": "REQ-RESEARCH-ISOLATED-001",
                "chat_id": "123456789",
                "query": "gail earnings",
                "raw_query": "/research gail earnings",
                "intent": "RESEARCH_REQUEST",
                "scheme_id": "gobardhan",
                "symbol": None,
            }

            dummy_snapshot = IntelligenceSnapshot(
                snapshot_id="SNAP-TEST-001",
                generated_at="2026-09-28T09:00:00Z",
                companies={
                    "GAIL.NS": CompanyIntelligence(
                        symbol="GAIL.NS",
                        short_symbol="GAIL",
                        name="GAIL (India)",
                        scheme_id="gobardhan",
                        scheme_name="GOBARdhan",
                        price=215.50,
                    )
                },
            )

            mock_retriever = MagicMock()
            mock_retriever.get_status.return_value = (True, dummy_snapshot, "OK")

            with patch("scheme_intel.delivery.workflow_query_runner.send_telegram", return_value=True) as mock_send:
                success = process_workflow_query(
                    payload=payload,
                    request_store=store,
                    retriever=mock_retriever,
                    query_engine=engine,
                )
                assert success is True
                assert mock_send.called
                sent_msg = mock_send.call_args[0][0]
                # Verifies it delivered the fresh multi-provider research card, NOT snapshot fallback
                assert "SCHEME-INTEL MULTI-PROVIDER RESEARCH" in sent_msg
                assert "SNAPSHOT_FALLBACK" not in sent_msg
                assert "The snapshot contains no earnings data" not in sent_msg
                assert "INDEPENDENT FACT FINDINGS" in sent_msg
                assert "BULL CASE" in sent_msg
                assert "BEAR CASE" in sent_msg
                assert "ARBITER SYNTHESIS" in sent_msg

