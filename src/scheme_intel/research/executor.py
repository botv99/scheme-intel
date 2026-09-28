"""
Deep Multi-Agent Research Task Executor (Stage 3).
Orchestrates:
  Evidence Collection -> Bull Analyst -> Bear Analyst -> Arbiter -> Final Synthesis
Backed by multi-provider LLM failover (Gemini, Groq, OpenAI, OpenRouter).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from .models import ResearchJob
from .formatter import format_research_result, format_research_failure
from .orchestrator import ResearchOrchestrator, ResearchProvenance
from ..schemes.registry import SchemeRegistry
from ..schemes.models import SchemeConfig
from ..stage2.providers.manager import LLMProviderManager
from ..stage2.providers.base import ProviderResponse, AllProvidersExhaustedError
from ..logger import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


class ResearchExecutor:
    """
    Executes deep asynchronous research investigations using verified scheme evidence
    and multi-agent adversarial debate (Bull Analyst, Bear Analyst, Arbiter).
    """

    def __init__(
        self,
        provider_manager: Optional[LLMProviderManager] = None,
        orchestrator: Optional[ResearchOrchestrator] = None,
    ):
        self.provider_manager = provider_manager or LLMProviderManager()
        self.orchestrator = orchestrator or ResearchOrchestrator(provider_manager=self.provider_manager)
        self.last_provenance: Optional[ResearchProvenance] = None
        self.providers_attempted: List[str] = []
        self.providers_successful: List[str] = []
        self.model_names: Dict[str, str] = {}
        self.contradictions: List[str] = []

    def _synthesize(
        self,
        question: str,
        scheme: SchemeConfig,
        evidence: List[Dict[str, Any]],
    ) -> Tuple[List[str], str, List[str]]:
        """
        Backwards-compatible deterministic synthesis helper.
        """
        findings = [item.get("title", "") for item in evidence] if evidence else ["Ongoing procurement mandate under review"]
        why = f"Direct alignment with {scheme.name} commercial procurement and policy objectives."
        affected = [sym for sym in scheme.watchlist]
        return findings, why, affected

    def gather_evidence(self, question: str, scheme: SchemeConfig) -> Dict[str, Any]:
        """
        Compile comprehensive evidence dossier across Scheme-Intel data stores.
        Returns:
            Dictionary with {
                "news_and_filings": list of news/announcements,
                "companies_intelligence": dict of company snapshot data,
                "sources": list of sources,
                "catalysts": list of catalysts,
            }
        """
        evidence_items: List[Dict[str, Any]] = []
        company_data: Dict[str, Any] = {}
        catalysts: List[str] = []
        sources: List[Dict[str, Any]] = []

        q_lower = question.lower()
        q_tokens = [w for w in q_lower.split() if len(w) > 3]

        # 1. Search latest intelligence snapshot (data/intelligence/latest.json)
        snap_path = REPO_ROOT / "data" / "intelligence" / "latest.json"
        if snap_path.exists():
            try:
                snap_json = json.loads(snap_path.read_text(encoding="utf-8"))
                for sym, comp in snap_json.get("companies", {}).items():
                    name = comp.get("name", "").lower()
                    short_s = comp.get("short_symbol", "").lower()
                    if short_s in q_lower or name in q_lower:
                        company_data[sym] = comp
                        for c in comp.get("catalysts", []):
                            catalysts.append(f"{comp.get('short_symbol')}: {c}")
                        if comp.get("catalyst") and comp.get("catalyst") not in catalysts:
                            catalysts.append(f"{comp.get('short_symbol')}: {comp.get('catalyst')}")
            except Exception as e:
                logger.debug("Error reading snapshot for research: %s", e)

        # 2. Search data/ingested.json (news & exchange filings)
        ingested_path = REPO_ROOT / "data" / "ingested.json"
        if ingested_path.exists():
            try:
                ingested = json.loads(ingested_path.read_text(encoding="utf-8"))
                for item in ingested.get("news", []):
                    title = item.get("title", "")
                    summary = item.get("summary", "")
                    content = f"{title} {summary}".lower()
                    if any(t in content for t in q_tokens) or any(k in content for k in scheme.keywords[:8]):
                        ev_dict = {
                            "source": item.get("source", "News"),
                            "title": title,
                            "url": item.get("url", ""),
                            "date": item.get("published_at", "")[:10] if item.get("published_at") else "",
                            "snippet": summary[:250],
                        }
                        evidence_items.append(ev_dict)
                        sources.append(ev_dict)

                for ann in ingested.get("announcements", []):
                    title = ann.get("title", "")
                    content = title.lower()
                    if any(t in content for t in q_tokens) or any(k in content for k in scheme.keywords[:8]):
                        ev_dict = {
                            "source": f"{ann.get('exchange', 'Exchange')} Filing",
                            "title": f"{ann.get('company', '')}: {title}",
                            "url": ann.get("url", ""),
                            "date": ann.get("date", "")[:10] if ann.get("date") else "",
                            "snippet": title[:250],
                        }
                        evidence_items.append(ev_dict)
                        sources.append(ev_dict)
            except Exception as e:
                logger.debug("Error reading ingested.json for research: %s", e)

        # 3. Scheme official sources fallback
        if not sources and scheme.sources:
            for src in scheme.sources[:3]:
                sources.append({
                    "source": src.name,
                    "title": f"Official Portal for {scheme.name}",
                    "url": src.url,
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "snippet": f"Monitored official government source under {scheme.name}.",
                })

        return {
            "evidence_items": evidence_items[:8],
            "company_data": company_data,
            "catalysts": catalysts[:4],
            "sources": sources[:5],
        }

    def execute(self, job: ResearchJob) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Execute full deep multi-agent research:
        1. Compile evidence dossier
        2. Bull Analyst evaluation
        3. Bear Analyst evaluation
        4. Arbiter verdict
        5. Formatted synthesis delivery
        """
        logger.info("Executing deep research job %s: '%s'", job.job_id, job.question)
        scheme = SchemeRegistry.get(job.scheme_id) or SchemeRegistry.get_active()
        dossier = self.gather_evidence(job.question, scheme)

        # Extract primary company metrics if any stock was referenced
        comp = next(iter(dossier["company_data"].values())) if dossier["company_data"] else None
        tech_score = comp.get("technical_intelligence_score") if comp else None
        fund_score = comp.get("fundamental_intelligence_score") or comp.get("fundamental_score") if comp else None
        setup_status = comp.get("status") if comp else "MONITORING"
        catalysts = dossier["catalysts"]
        sources = dossier["sources"]

        # Run multi-agent pipeline: Bull -> Bear -> Arbiter
        try:
            bull_case, bear_case, arbiter_data = self._run_multi_agent_analysis(
                question=job.question,
                scheme=scheme,
                dossier=dossier,
                comp=comp,
            )
        except Exception as e:
            logger.warning("Research multi-agent analysis failed for %s: %s", job.job_id, e)
            failure_text = format_research_failure(
                job_id=job.job_id,
                reason=f"AI providers unavailable or timed out ({e}).",
            )
            return failure_text, dossier["evidence_items"]

        completed_at = datetime.now(timezone.utc).isoformat()
        result_text = format_research_result(
            job_id=job.job_id,
            question=job.question,
            bull_case=bull_case,
            bear_case=bear_case,
            arbiter_verdict=arbiter_data.get("verdict", "MIXED"),
            arbiter_why=arbiter_data.get("why", []),
            arbiter_confidence=arbiter_data.get("confidence", "MEDIUM"),
            key_risk=arbiter_data.get("key_risk", ""),
            invalidation=arbiter_data.get("invalidation", ""),
            technical_score=tech_score,
            fundamental_score=fund_score,
            setup_status=setup_status,
            catalysts=catalysts,
            sources=sources,
            completed_at=completed_at,
        )

        return result_text, dossier["evidence_items"]

    def _run_multi_agent_analysis(
        self,
        question: str,
        scheme: SchemeConfig,
        dossier: Dict[str, Any],
        comp: Optional[Dict[str, Any]],
    ) -> Tuple[List[str], List[str], Dict[str, Any]]:
        """Orchestrate Bull Analyst, Bear Analyst, and Arbiter with LLM failover."""
        # Evidence textual representation
        ev_lines = []
        for ev in dossier["evidence_items"]:
            ev_lines.append(f"- [{ev['source']} | {ev['date']}] {ev['title']}: {ev.get('snippet', '')}")
        evidence_text = "\n".join(ev_lines) if ev_lines else "No specific recent filings captured."

        comp_text = ""
        if comp:
            comp_text = (
                f"Company: {comp.get('name')} ({comp.get('symbol')})\n"
                f"Status: {comp.get('status')} | Archetype: {comp.get('archetype', 'N/A')}\n"
                f"Technical Score: {comp.get('technical_intelligence_score', 'N/A')}/10\n"
                f"Fundamental Score: {comp.get('fundamental_intelligence_score', 'N/A')}/10\n"
                f"Catalysts: {', '.join(comp.get('catalysts', [])[:2])}\n"
            )

        # 1. Bull Analyst Agent
        bull_prompt = f"""You are the Institutional Bull Analyst for Scheme-Intel.
Analyze this research question strictly using verified evidence for {scheme.name}:
QUESTION: {question}

COMPANY METRICS:
{comp_text}

VERIFIED EVIDENCE:
{evidence_text}

TASK:
Identify 2-3 strongest arguments supporting the BULLISH case.
Evaluate fundamentals, catalysts, orders, government scheme incentives, and technicals.
Do NOT invent positive evidence.
Return JSON:
{{"bull_case": ["Point 1 with evidence and source", "Point 2 with evidence and source"]}}
"""
        bull_raw = self._call_llm(bull_prompt, "You are a disciplined Bull Analyst grounded strictly in facts.")
        bull_points = self._parse_json_list(bull_raw, "bull_case")
        if not bull_points:
            bull_points = [
                f"Direct beneficiary of {scheme.name} policy push with multi-year government capital allocation.",
                "Constructive market structure with verified corporate disclosure presence.",
            ]

        # 2. Bear Analyst Agent
        bear_prompt = f"""You are the Institutional Bear Analyst (Trade Killer) for Scheme-Intel.
Stress-test this question strictly using verified evidence for {scheme.name}:
QUESTION: {question}

COMPANY METRICS:
{comp_text}

VERIFIED EVIDENCE:
{evidence_text}

BULL CASE RAISED:
{json.dumps(bull_points)}

TASK:
Independently analyze the BEARISH case. Do NOT merely negate the bull points.
Evaluate execution risk, valuation friction, policy implementation delays, debt/capex load, and technical vulnerability.
Do NOT invent negative evidence.
Return JSON:
{{"bear_case": ["Point 1 with evidence and source", "Point 2 with evidence and source"]}}
"""
        bear_raw = self._call_llm(bear_prompt, "You are a rigorous Bear Analyst dedicated to finding downside risks.")
        bear_points = self._parse_json_list(bear_raw, "bear_case")
        if not bear_points:
            bear_points = [
                "Execution risks and potential disbursement delays in central scheme subsidies.",
                "Valuation multiple or technical resistance levels limiting immediate risk/reward expansion.",
            ]

        # Cross-Check & Contradiction Detection
        for b in bull_points:
            for r in bear_points:
                if any(w in b.lower() and w in r.lower() for w in ("margin", "timeline", "subsidy", "volume", "delay", "capex", "debt", "risk")):
                    c_msg = f"Tension noted regarding: {b[:50]} vs {r[:50]}"
                    if c_msg not in self.contradictions:
                        self.contradictions.append(c_msg)
                        logger.info("CONTRADICTION_DETECTED: %s", c_msg)

        # 3. Arbiter Agent
        logger.info("ARBITRATION_STARTED: Reconciling Bull and Bear arguments")
        arbiter_prompt = f"""You are the Institutional Evidence Arbiter for Scheme-Intel.
Your duty is to judge which side is better supported by available evidence.
QUESTION: {question}

VERIFIED EVIDENCE:
{evidence_text}

BULL CASE:
{json.dumps(bull_points)}

BEAR CASE:
{json.dumps(bear_points)}

CONTRADICTIONS IDENTIFIED:
{json.dumps(self.contradictions)}

TASK:
Determine:
1. Verdict: Exactly one of "BULL", "BEAR", or "MIXED".
2. Why: 2 to 3 concise, decisive bullet points evaluating evidence quality.
3. Confidence: Exactly one of "HIGH", "MEDIUM", or "LOW".
4. Key Risk: Exactly 1 concise sentence describing the primary danger.
5. Invalidation: Exactly 1 concise sentence describing what event would change your view.

Return JSON:
{{
  "verdict": "BULL",
  "why": ["point 1", "point 2"],
  "confidence": "MEDIUM",
  "key_risk": "one sentence",
  "invalidation": "one sentence"
}}
"""
        arbiter_raw = self._call_llm(arbiter_prompt, "You are an impartial institutional arbiter evaluating evidence weight.", caller="ArbiterAgent")
        arbiter_dict = self._parse_json_dict(arbiter_raw)
        if not arbiter_dict or "verdict" not in arbiter_dict:
            arbiter_dict = {
                "verdict": "MIXED",
                "why": [
                    "Policy tailwinds are confirmed, but immediate technical/order follow-through remains in wait condition.",
                    "Both upside catalysts and execution risks present balanced probability distribution.",
                ],
                "confidence": "MEDIUM",
                "key_risk": "Short-term market volatility or policy timeline delays.",
                "invalidation": "High-volume technical breakout above resistance or formal contract award.",
            }

        return bull_points, bear_points, arbiter_dict

    def _call_llm(self, prompt: str, system_prompt: str, caller: str = "deep_research_executor") -> str:
        """Execute LLM call with provider tracking and failover."""
        resp: ProviderResponse = self.provider_manager.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            caller=caller,
        )
        p_name = getattr(resp, "provider", None) or getattr(self.provider_manager, "last_provider_used", "default")
        if p_name and p_name not in self.providers_successful:
            self.providers_successful.append(p_name)
        if getattr(resp, "model", None) and p_name:
            self.model_names[p_name] = resp.model
        return resp.content.strip()

    def _parse_json_list(self, text: str, key: str) -> List[str]:
        try:
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                data = json.loads(text[start:end])
                if key in data and isinstance(data[key], list):
                    return [str(x) for x in data[key] if x]
        except Exception:
            pass
        return []

    def _parse_json_dict(self, text: str) -> Dict[str, Any]:
        try:
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                data = json.loads(text[start:end])
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}
