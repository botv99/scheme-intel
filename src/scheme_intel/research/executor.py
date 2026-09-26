"""
Deep Research Task Executor.
Gathers evidence across scheme-specific sources and performs evidence-grounded LLM synthesis.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from .models import ResearchJob
from .formatter import format_research_result
from ..schemes.registry import SchemeRegistry
from ..schemes.models import SchemeConfig
from ..stage2.providers.manager import LLMProviderManager
from ..stage2.providers.base import ProviderResponse
from ..logger import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


class ResearchExecutor:
    """Executes asynchronous research investigations using verified scheme evidence."""

    def __init__(self, provider_manager: Optional[LLMProviderManager] = None):
        self.provider_manager = provider_manager or LLMProviderManager()

    def gather_evidence(self, question: str, scheme: SchemeConfig) -> List[Dict[str, Any]]:
        """
        Gather verified evidence snippets matching the question from scheme sources and ingested history.
        """
        evidence: List[Dict[str, Any]] = []
        q_tokens = [w.lower() for w in question.split() if len(w) > 3]

        # 1. Search data/ingested.json
        ingested_path = REPO_ROOT / "data" / "ingested.json"
        if ingested_path.exists():
            try:
                data = json.loads(ingested_path.read_text(encoding="utf-8"))
                for item in data.get("news", []):
                    title = item.get("title", "")
                    summary = item.get("summary", "")
                    content = f"{title} {summary}".lower()
                    if any(t in content for t in q_tokens) or any(k in content for k in scheme.keywords[:10]):
                        evidence.append({
                            "source": item.get("source", "News"),
                            "title": title,
                            "url": item.get("url", ""),
                            "date": item.get("published_at", "")[:10] if item.get("published_at") else "",
                            "snippet": summary[:200],
                        })
                for ann in data.get("announcements", []):
                    title = ann.get("title", "")
                    content = title.lower()
                    if any(t in content for t in q_tokens) or any(k in content for k in scheme.keywords[:10]):
                        evidence.append({
                            "source": f"{ann.get('exchange', 'NSE')} Disclosure",
                            "title": f"{ann.get('company', '')}: {title}",
                            "url": ann.get("url", ""),
                            "date": ann.get("date", "")[:10] if ann.get("date") else "",
                            "snippet": title[:200],
                        })
            except Exception as e:
                logger.debug("Error reading ingested.json for research: %s", e)

        # 2. Add scheme official source references if evidence is sparse
        if not evidence and scheme.sources:
            for src in scheme.sources[:3]:
                evidence.append({
                    "source": src.name,
                    "title": f"Official Portal for {scheme.name}",
                    "url": src.url,
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "snippet": f"Monitored official government source under {scheme.name}.",
                })

        return evidence[:8]

    def execute(self, job: ResearchJob) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Execute deep research for a queued job.
        Gathers evidence, synthesizes with LLM under strict anti-hallucination rules, and formats output.
        """
        logger.info("Executing research job %s: '%s'", job.job_id, job.question)
        scheme = SchemeRegistry.get(job.scheme_id) or SchemeRegistry.get_active()
        evidence = self.gather_evidence(job.question, scheme)

        # Synthesize using LLM or deterministic fallback
        findings, why_it_matters, affected_companies = self._synthesize(
            job.question, scheme, evidence
        )

        completed_at = datetime.now(timezone.utc).isoformat()
        result_text = format_research_result(
            job_id=job.job_id,
            question=job.question,
            findings=findings,
            why_it_matters=why_it_matters,
            companies_affected=affected_companies,
            evidence=evidence,
            completed_at=completed_at,
        )

        return result_text, evidence

    def _synthesize(
        self,
        question: str,
        scheme: SchemeConfig,
        evidence: List[Dict[str, Any]],
    ) -> Tuple[str, str, List[str]]:
        """Run constrained LLM synthesis or deterministic synthesis."""
        # Detect companies mentioned in question or evidence
        watchlist_symbols = [s.symbol.split(".")[0] for s in scheme.watchlist]
        affected: List[str] = []
        for stock in scheme.watchlist:
            short_s = stock.symbol.split(".")[0]
            if short_s.lower() in question.lower() or stock.name.lower() in question.lower():
                affected.append(f"{short_s} ({stock.name}) — Direct policy beneficiary")
            else:
                for ev in evidence:
                    if short_s.lower() in ev["title"].lower() or stock.name.lower() in ev["title"].lower():
                        affected.append(f"{short_s} ({stock.name}) — Active contract/tender mentions")
                        break
        affected = list(dict.fromkeys(affected))[:5]

        # Prepare evidence text
        ev_summary = "\n".join([
            f"- [{ev['source']} {ev['date']}] {ev['title']}: {ev.get('snippet', '')}"
            for ev in evidence
        ]) if evidence else "No recent external evidence recorded."

        prompt = f"""You are Scheme-Intel's Deep Research Intelligence Unit.
Analyze the following policy question strictly within the context of the {scheme.name}.

QUESTION: {question}

AVAILABLE VERIFIED EVIDENCE:
{ev_summary}

RULES:
1. Synthesize factual findings based ONLY on the evidence above and official policy domain knowledge.
2. Do NOT invent fake press releases, dates, or prices.
3. If evidence is insufficient, explicitly state: "Limited verified developments detected in the monitoring window."
4. Return a structured JSON response with keys:
   - "findings": string (concise bulleted or numbered points)
   - "why_it_matters": string (brief commercial & market relevance)
"""

        try:
            resp: ProviderResponse = self.provider_manager.generate(
                prompt=prompt,
                system_prompt="You are an institutional research analyst. Ground all answers strictly in facts.",
                temperature=0.2,
                caller="research_executor",
            )
            raw = resp.content.strip()
            # If JSON parseable
            if "{" in raw and "}" in raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                parsed = json.loads(raw[start:end])
                findings = parsed.get("findings", "")
                why = parsed.get("why_it_matters", "")
                if findings:
                    return findings, why, affected
            return raw, "Monitored policy initiative affecting scheme participants.", affected
        except Exception as e:
            logger.debug("LLM synthesis unavailable or failed (%s); using deterministic evidence synthesis.", e)
            if evidence:
                lines = [f"{i+1}. {ev['title']} ({ev['source']}, {ev['date']})" for i, ev in enumerate(evidence[:3])]
                findings = "\n".join(lines)
                why = f"Directly impacts procurement, subsidy allocation, and commercial execution under {scheme.name}."
            else:
                findings = f"No material policy shifts detected for {scheme.name} in the current monitoring window."
                why = "Scheme fundamentals remain stable without new regulatory disruptions."
            return findings, why, affected
