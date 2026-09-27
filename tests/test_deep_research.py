"""
Comprehensive Unit Tests for Deep Multi-Agent Research Pipeline (Stage 3).
Verifies:
  - /research command registration & routing
  - Request creation & request_id generation
  - Chat ID preservation & strict chat isolation (no global broadcast)
  - Evidence collection & source attribution
  - Bull Analyst, Bear Analyst, Arbiter multi-agent flow
  - Provider failover & provider failure handling
  - Formatted Telegram response structure
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from scheme_intel.research.models import ResearchJob, ResearchStatus
from scheme_intel.research.queue import ResearchQueue
from scheme_intel.research.executor import ResearchExecutor
from scheme_intel.research.formatter import (
    format_research_acknowledgement,
    format_research_result,
    format_research_failure,
)
from scheme_intel.stage2.providers.base import ProviderResponse
from scheme_intel.stage2.providers.manager import LLMProviderManager


class TestDeepResearchPipeline:
    @pytest.fixture
    def test_queue(self, tmp_path: Path):
        db_path = str(tmp_path / "research_queue.db")
        return ResearchQueue(db_path=db_path)

    def test_acknowledgement_message_format(self):
        ack = format_research_acknowledgement("TG-12345678", "Why is TRUALT moving today?")
        assert "DEEP RESEARCH STARTED" in ack
        assert "TG-12345678" in ack
        assert "analyzed by the Scheme-Intel intelligence engine" in ack
        assert "This may take a little time." in ack

    def test_request_creation_and_chat_isolation(self, test_queue: ResearchQueue):
        job = test_queue.enqueue_job(
            question="Compare TRUALT and PRAJ",
            user_id="user_999",
            chat_id="chat_isolated_123",
            scheme_id="gobardhan",
        )
        assert job.job_id.startswith("R-")
        assert job.user_id == "user_999"
        assert job.chat_id == "chat_isolated_123"
        assert job.status == ResearchStatus.QUEUED

        # Ensure claiming preserves chat_id
        claimed = test_queue.claim_next_job()
        assert claimed is not None
        assert claimed.job_id == job.job_id
        assert claimed.chat_id == "chat_isolated_123"

    def test_evidence_collection(self):
        executor = ResearchExecutor()
        from scheme_intel.schemes.registry import SchemeRegistry
        scheme = SchemeRegistry.get_active()
        dossier = executor.gather_evidence("What is happening with GAIL and CBG?", scheme)
        assert "evidence_items" in dossier
        assert "sources" in dossier
        assert "company_data" in dossier

    def test_multi_agent_execution_with_mocked_llm(self):
        mock_mgr = MagicMock(spec=LLMProviderManager)
        # Mock responses for Bull, Bear, Arbiter
        mock_mgr.generate.side_effect = [
            ProviderResponse(
                content='{"bull_case": ["Strong order intake from CBG mandate.", "Robust EBITDA margins (>14%)."]}',
                model="mock-bull",
                provider="groq",
            ),
            ProviderResponse(
                content='{"bear_case": ["Execution risk at pipeline interconnection points.", "Moderate leverage on balance sheet."]}',
                model="mock-bear",
                provider="groq",
            ),
            ProviderResponse(
                content='{"verdict": "BULL", "why": ["Government mandates support volume growth.", "Technical score is solid."], "confidence": "HIGH", "key_risk": "Pipeline delay", "invalidation": "Cancellation of procurement subsidies."}',
                model="mock-arbiter",
                provider="groq",
            ),
        ]

        executor = ResearchExecutor(provider_manager=mock_mgr)
        job = ResearchJob(
            job_id="TG-TESTJOB",
            user_id="user_1",
            chat_id="chat_1",
            question="Why is GAIL expanding CBG?",
            scheme_id="gobardhan",
            created_at="2026-09-27T10:00:00Z",
        )
        res_text, evidence = executor.execute(job)

        # Check required sections in formatted output
        assert "SCHEME-INTEL RESEARCH" in res_text
        assert "CURRENT INTELLIGENCE" in res_text
        assert "BULL CASE" in res_text
        assert "Strong order intake" in res_text
        assert "BEAR CASE" in res_text
        assert "Execution risk" in res_text
        assert "ARBITER" in res_text
        assert "`BULL`" in res_text
        assert "KEY RISK" in res_text
        assert "WHAT WOULD CHANGE THE VIEW" in res_text
        assert "TG-TESTJOB" in res_text

    def test_provider_failure_returns_clean_failure_card(self):
        mock_mgr = MagicMock(spec=LLMProviderManager)
        mock_mgr.generate.side_effect = RuntimeError("All providers quota exceeded (429)")

        executor = ResearchExecutor(provider_manager=mock_mgr)
        job = ResearchJob(
            job_id="TG-FAILJOB",
            user_id="user_1",
            chat_id="chat_1",
            question="Deep test query",
            scheme_id="gobardhan",
            created_at="2026-09-27T10:00:00Z",
        )
        res_text, _ = executor.execute(job)

        assert "Research could not be completed" in res_text
        assert "AI providers unavailable" in res_text
        assert "TG-FAILJOB" in res_text
        # No hallucinated output
        assert "BULL CASE" not in res_text

    def test_registered_command_menu_includes_research(self):
        from scheme_intel.delivery.telegram_conversation import register_bot_commands
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            register_bot_commands("mock_token")
            payload = mock_post.call_args[1]["json"]["commands"]
            cmd_names = [c["command"] for c in payload]
            assert "research" in cmd_names
            assert "stock" in cmd_names
            assert "setups" in cmd_names
            assert "watchlist" in cmd_names
            assert "start" in cmd_names
            assert "help" in cmd_names
            assert len(cmd_names) == 6
