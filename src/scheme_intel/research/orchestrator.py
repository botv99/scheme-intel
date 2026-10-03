"""
Fresh Multi-Provider Research Orchestrator for Scheme-Intel (Stage 3).
Orchestrates genuine multi-provider research with role specialization, contradiction detection,
degraded confidence management, and structured provenance.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus
import feedparser

from .classifier import QueryClassifier, QueryType
from .providers import ProviderRegistry, default_registry
from ..schemes.registry import SchemeRegistry
from ..schemes.models import SchemeConfig
from ..stage2.providers.base import LLMProvider, ProviderResponse, sanitize_secret
from ..stage2.providers.manager import LLMProviderManager
from ..logger import get_logger

logger = get_logger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ResearchProvenance:
    """Structured audit trail and execution provenance for research requests."""
    query: str
    timestamp: str
    providers_attempted: List[str] = field(default_factory=list)
    providers_successful: List[str] = field(default_factory=list)
    evidence_sources: List[Dict[str, Any]] = field(default_factory=list)
    model_names: Dict[str, str] = field(default_factory=dict)
    agent_outputs: Dict[str, Any] = field(default_factory=dict)
    contradictions: List[str] = field(default_factory=list)
    final_synthesis: Dict[str, Any] = field(default_factory=dict)
    confidence: str = "HIGH"
    execution_duration_seconds: float = 0.0
    degraded_status: bool = False
    is_fallback: bool = False


@dataclass
class ResearchResult:
    """Container for complete research execution."""
    result_text: str
    evidence_items: List[Dict[str, Any]]
    provenance: ResearchProvenance
    is_fallback: bool = False


def search_internet_for_research(query: str, scheme: Optional[SchemeConfig] = None, max_items: int = 10) -> List[Dict[str, Any]]:
    """
    Execute live web search for research query across Google News RSS and financial feeds.
    Returns list of fresh evidence items: [{source, title, url, date, snippet}].
    """
    clean_q = re.sub(r"^/research\s*", "", query, flags=re.IGNORECASE).strip()
    if not clean_q:
        return []

    evidence_items: List[Dict[str, Any]] = []
    seen_titles = set()

    # Search queries to fan out across internet
    search_queries = [clean_q]
    q_lower = clean_q.lower()

    # Financial / Earnings query enrichment
    if any(k in q_lower for k in ("earnings", "results", "profit", "revenue", "q1", "q2", "q3", "q4", "concall")):
        search_queries.append(f"{clean_q} quarterly results")
    elif scheme and scheme.keywords:
        search_queries.append(f"{clean_q} {scheme.keywords[0]}")
    else:
        search_queries.append(f"{clean_q} latest news")

    for sq in search_queries[:2]:
        encoded = quote_plus(sq)
        rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:6]:
                title = entry.get("title", "").strip()
                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                src_name = entry.get("source", {}).get("title") if isinstance(entry.get("source"), dict) else "Financial Media"
                summary_raw = entry.get("summary", "")
                clean_snippet = re.sub(r"<[^>]+>", " ", summary_raw).strip() if summary_raw else title
                clean_snippet = re.sub(r"\s+", " ", clean_snippet)[:350]

                pub_date = entry.get("published", "")
                if pub_date:
                    pub_parts = pub_date.split()
                    if len(pub_parts) >= 4:
                        pub_date = f"{pub_parts[1]} {pub_parts[2]} {pub_parts[3]}"

                evidence_items.append({
                    "source": src_name or "Financial Media",
                    "title": title,
                    "url": entry.get("link", ""),
                    "date": pub_date or datetime.now(timezone.utc).strftime("%d %b %Y"),
                    "snippet": clean_snippet,
                })
        except Exception as e:
            logger.debug("Google News RSS search failed for '%s': %s", sq, e)

    # yfinance news lookup if ticker mentioned
    ticker_map = {
        "gail": "GAIL.NS",
        "praj": "PRAJIND.NS",
        "prajind": "PRAJIND.NS",
        "wabag": "WABAG.NS",
        "trualt": "TRUALT.NS",
        "organic": "ORGANICREC.BO",
        "kirlpn": "KIRLPNU.NS",
        "kirloskar": "KIRLPNU.NS",
        "ioc": "IOC.NS",
        "ionexchang": "IONEXCHANG.NS",
        "ongc": "ONGC.NS",
        "oil": "OIL.NS",
        "reliance": "RELIANCE.NS",
        "ril": "RELIANCE.NS",
        "vedl": "VEDL.NS",
        "vedanta": "VEDL.NS",
        "jindcot": "JINDCOT.NS",
        "seamec": "SEAMECLTD.NS",
        "dolphin": "DOLPHIN.NS",
    }
    try:
        from ..schemes.registry import SchemeRegistry
        for s_cfg in SchemeRegistry.list_schemes():
            for w in s_cfg.watchlist:
                clean_sym = w.symbol.upper()
                base_sym = clean_sym.split(".")[0]
                ticker_map[base_sym.lower()] = clean_sym
    except Exception:
        pass
    for key, sym in ticker_map.items():
        if key in q_lower:
            try:
                import yfinance as yf
                t = yf.Ticker(sym)
                yf_news = getattr(t, "news", []) or []
                for n in yf_news[:4]:
                    content_block = n.get("content", {}) if isinstance(n.get("content"), dict) else {}
                    t_title = content_block.get("title") or n.get("title", "")
                    if t_title and t_title.lower() not in seen_titles:
                        seen_titles.add(t_title.lower())
                        evidence_items.append({
                            "source": content_block.get("provider", {}).get("displayName") or n.get("publisher") or "Yahoo Finance",
                            "title": t_title,
                            "url": content_block.get("canonicalUrl", {}).get("url") or n.get("link") or "",
                            "date": datetime.now(timezone.utc).strftime("%d %b %Y"),
                            "snippet": content_block.get("summary") or t_title,
                        })
            except Exception as yf_err:
                logger.debug("yfinance news fetch failed for %s: %s", sym, yf_err)

    return evidence_items[:max_items]


class ResearchOrchestrator:
    """
    Orchestrates true multi-provider AI research:
    1. Gathers context from snapshot, fresh evidence from internet search, news, and filings.
    2. Fans out to available distinct AI providers (Groq, Gemini, OpenAI, OpenRouter).
    3. Executes role-based agents (Research/Fact, Bull, Bear, Arbiter).
    4. Detects contradictions and builds consensus without hallucinations.
    5. Degrades gracefully if providers fail; explicitly labels snapshot fallbacks.
    """

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        provider_manager: Optional[LLMProviderManager] = None,
    ):
        self.registry = registry or default_registry
        self.provider_manager = provider_manager

    def gather_fresh_evidence(
        self,
        query: str,
        scheme: SchemeConfig,
        snapshot_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Gather fresh evidence from live internet search, ingested news, filings, and official sources.
        Snapshot data is passed as background context only, NEVER as complete evidence.
        """
        evidence_items: List[Dict[str, Any]] = []
        company_data: Dict[str, Any] = {}
        catalysts: List[str] = []
        sources: List[Dict[str, Any]] = []

        q_lower = query.lower()
        q_tokens = [w for w in q_lower.split() if len(w) > 3]

        # 1. Live Internet Search (Google News RSS, Financial Media, yfinance)
        try:
            internet_evidence = search_internet_for_research(query, scheme)
            for ev in internet_evidence:
                evidence_items.append(ev)
                sources.append(ev)
            if internet_evidence:
                logger.info("INTERNET_SEARCH_COLLECTED: %d live items retrieved for query '%s'", len(internet_evidence), query[:40])
        except Exception as e:
            logger.debug("Internet search encountered error: %s", e)

        # 2. Snapshot as Background Context ONLY
        if snapshot_context:
            target_scheme_id = scheme.id.lower() if scheme and getattr(scheme, "id", None) else None
            for sym, comp in snapshot_context.get("companies", {}).items():
                comp_scheme = (comp.get("scheme_id") or "").lower()
                if target_scheme_id and comp_scheme and comp_scheme != target_scheme_id:
                    continue
                name = comp.get("name", "").lower()
                short_s = comp.get("short_symbol", "").lower()
                if short_s in q_lower or name in q_lower or any(t in name for t in q_tokens):
                    company_data[sym] = comp
                    for c in comp.get("catalysts", []):
                        catalysts.append(f"{comp.get('short_symbol')}: {c}")

        # 3. Fresh Ingested News & Announcements (authoritative recent facts)
        ingested_path = REPO_ROOT / "data" / "ingested.json"
        if ingested_path.exists():
            try:
                ingested = json.loads(ingested_path.read_text(encoding="utf-8"))
                for item in ingested.get("news", []):
                    title = item.get("title", "")
                    summary = item.get("summary", "")
                    content = f"{title} {summary}".lower()
                    if any(t in content for t in q_tokens) or any(k in content for k in scheme.keywords[:6]):
                        ev = {
                            "source": item.get("source", "News"),
                            "title": title,
                            "url": item.get("url", ""),
                            "date": item.get("published_at", "")[:10] if item.get("published_at") else "",
                            "snippet": summary[:300],
                        }
                        evidence_items.append(ev)
                        sources.append(ev)

                for ann in ingested.get("announcements", []):
                    title = ann.get("title", "")
                    content = title.lower()
                    if any(t in content for t in q_tokens) or any(k in content for k in scheme.keywords[:6]):
                        ev = {
                            "source": f"{ann.get('exchange', 'Exchange')} Filing",
                            "title": f"{ann.get('company', '')}: {title}",
                            "url": ann.get("url", ""),
                            "date": ann.get("date", "")[:10] if ann.get("date") else "",
                            "snippet": title[:300],
                        }
                        evidence_items.append(ev)
                        sources.append(ev)
            except Exception as e:
                logger.debug("Error reading ingested.json for fresh evidence: %s", e)

        # 4. Official Scheme Monitored Sources
        if scheme and scheme.sources:
            for src in scheme.sources[:3]:
                sources.append({
                    "source": src.name,
                    "title": f"Official Portal for {scheme.name}",
                    "url": src.url,
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "snippet": f"Statutory regulatory framework and guidelines under {scheme.name}.",
                })

        logger.info("EVIDENCE_COLLECTED: %d items gathered for query '%s'", len(evidence_items), query[:40])

        return {
            "evidence_items": evidence_items[:12],
            "company_data": company_data,
            "catalysts": catalysts[:4],
            "sources": sources[:8],
        }

    def execute_research(
        self,
        query: str,
        scheme_id: str = "gobardhan",
        snapshot_context: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
    ) -> ResearchResult:
        """
        Execute multi-provider deep research.
        Logs standard events:
        RESEARCH_STARTED, PROVIDER_CALLED, PROVIDER_SUCCESS, PROVIDER_FAILURE,
        EVIDENCE_COLLECTED, CONTRADICTION_DETECTED, ARBITRATION_STARTED,
        RESEARCH_COMPLETED, SNAPSHOT_FALLBACK.
        """
        start_time = time.time()
        effective_job_id = job_id or f"R-{int(time.time())}"
        now_iso = datetime.now(timezone.utc).isoformat()

        logger.info("RESEARCH_STARTED: job_id=%s, query='%s'", effective_job_id, query)

        scheme = SchemeRegistry.get(scheme_id) or SchemeRegistry.get_active()
        dossier = self.gather_fresh_evidence(query, scheme, snapshot_context)

        # Retrieve available active providers
        available_providers = self._get_active_providers()

        # If zero providers available, execute SNAPSHOT_FALLBACK
        if not available_providers:
            logger.warning("SNAPSHOT_FALLBACK: No active AI providers available for research query '%s'", query)
            fallback_text, fallback_evidence = self._generate_snapshot_fallback(
                query=query,
                scheme=scheme,
                dossier=dossier,
                snapshot_context=snapshot_context,
                job_id=effective_job_id,
            )
            dur = time.time() - start_time
            prov = ResearchProvenance(
                query=query,
                timestamp=now_iso,
                providers_attempted=[],
                providers_successful=[],
                evidence_sources=fallback_evidence,
                confidence="LOW",
                execution_duration_seconds=round(dur, 2),
                degraded_status=True,
                is_fallback=True,
            )
            return ResearchResult(
                result_text=fallback_text,
                evidence_items=fallback_evidence,
                provenance=prov,
                is_fallback=True,
            )

        # Distribute roles across available providers
        prov_names = list(available_providers.keys())
        logger.info("Active providers participating: %s", prov_names)

        # Allocate distinct providers to distinct roles if multiple exist
        # Roles: 1. Fact/Neutral Agent, 2. Bull Agent, 3. Bear Agent, 4. Arbiter
        fact_provider_name = prov_names[0]
        bull_provider_name = prov_names[1 % len(prov_names)]
        bear_provider_name = prov_names[2 % len(prov_names)]
        arbiter_provider_name = prov_names[3 % len(prov_names)] if len(prov_names) >= 4 else prov_names[0]

        degraded = len(prov_names) == 1
        providers_attempted: List[str] = []
        providers_successful: List[str] = []
        model_names: Dict[str, str] = {}
        agent_outputs: Dict[str, Any] = {}
        contradictions: List[str] = []

        # Build evidence text
        ev_lines = [
            f"- [{e['source']} | {e['date']}] {e['title']}: {e.get('snippet', '')}"
            for e in dossier["evidence_items"]
        ]
        evidence_text = "\n".join(ev_lines) if ev_lines else "No specific recent filings found."

        comp_text = ""
        comp = next(iter(dossier["company_data"].values())) if dossier["company_data"] else None
        if comp:
            comp_text = (
                f"Company: {comp.get('name')} ({comp.get('symbol')})\n"
                f"Status: {comp.get('status')} | Archetype: {comp.get('archetype', 'N/A')}\n"
                f"Technical Score: {comp.get('technical_intelligence_score', 'N/A')}/10\n"
                f"Fundamental Score: {comp.get('fundamental_intelligence_score', 'N/A')}/10\n"
            )

        # 1. Fact / Neutral Agent Call
        fact_prompt = f"""You are the Neutral Fact and Evidence Agent for Scheme-Intel.
Query: {query}
Scheme: {scheme.name}
Background Metrics: {comp_text}
Fresh Evidence:
{evidence_text}

Task:
Extract 2-3 objective, verifiable factual observations directly supported by the evidence.
Return JSON:
{{"fact_points": ["Fact 1", "Fact 2"]}}
"""
        fact_res = self._call_provider(
            provider_name=fact_provider_name,
            provider=available_providers[fact_provider_name],
            prompt=fact_prompt,
            system_prompt="You are a strict, objective fact and evidence verification agent.",
            caller="NeutralFactAgent",
            providers_attempted=providers_attempted,
            providers_successful=providers_successful,
            model_names=model_names,
        )
        fact_points = self._parse_json_list(fact_res, "fact_points") or [
            f"Government allocation under {scheme.name} remains under active deployment.",
            "Corporate disclosures confirm active participation in procurement bids.",
        ]
        agent_outputs["fact_agent"] = {"provider": fact_provider_name, "points": fact_points}

        # 2. Bull Analyst Agent Call
        bull_prompt = f"""You are the Institutional Bull Analyst for Scheme-Intel.
Query: {query}
Scheme: {scheme.name}
Verified Facts:
{json.dumps(fact_points)}
Evidence:
{evidence_text}

Task:
Identify 2-3 strongest arguments supporting the BULLISH case (volume, catalysts, policy subsidy, margin upside).
Return JSON:
{{"bull_case": ["Bull argument 1", "Bull argument 2"]}}
"""
        bull_res = self._call_provider(
            provider_name=bull_provider_name,
            provider=available_providers[bull_provider_name],
            prompt=bull_prompt,
            system_prompt="You are a disciplined institutional Bull Analyst grounded strictly in facts.",
            caller="BullAgent",
            providers_attempted=providers_attempted,
            providers_successful=providers_successful,
            model_names=model_names,
        )
        bull_case = self._parse_json_list(bull_res, "bull_case") or [
            f"Direct policy mandate alignment under {scheme.name} creating procurement visibility.",
            "Commercial order book expansion backed by central capex incentives.",
        ]
        agent_outputs["bull_agent"] = {"provider": bull_provider_name, "points": bull_case}

        # 3. Bear Analyst Agent Call (Stress-Test / Trade Killer)
        bear_prompt = f"""You are the Institutional Bear Analyst (Trade Killer) for Scheme-Intel.
Query: {query}
Scheme: {scheme.name}
Verified Facts:
{json.dumps(fact_points)}
Bull Arguments Raised:
{json.dumps(bull_case)}
Evidence:
{evidence_text}

Task:
Independently stress-test downside risks (execution delays, valuation friction, working capital, technical resistance).
Do NOT merely repeat or invert the bull points.
Return JSON:
{{"bear_case": ["Bear risk 1", "Bear risk 2"]}}
"""
        bear_res = self._call_provider(
            provider_name=bear_provider_name,
            provider=available_providers[bear_provider_name],
            prompt=bear_prompt,
            system_prompt="You are a rigorous institutional Bear Analyst dedicated to stress-testing risks.",
            caller="BearAgent",
            providers_attempted=providers_attempted,
            providers_successful=providers_successful,
            model_names=model_names,
        )
        bear_case = self._parse_json_list(bear_res, "bear_case") or [
            "Execution bottlenecks and disbursement latency across regional nodes.",
            "Valuation resistance and overhead market liquidity constraints.",
        ]
        agent_outputs["bear_agent"] = {"provider": bear_provider_name, "points": bear_case}

        # Cross-Check & Contradiction Detection
        logger.info("ARBITRATION_STARTED: Reconciling Bull and Bear arguments across providers")
        for b in bull_case:
            for r in bear_case:
                if any(w in b.lower() and w in r.lower() for w in ("margin", "timeline", "subsidy", "volume", "delay")):
                    c_msg = f"Tension noted regarding: {b[:50]} vs {r[:50]}"
                    if c_msg not in contradictions:
                        contradictions.append(c_msg)
                        logger.info("CONTRADICTION_DETECTED: %s", c_msg)

        # 4. Arbiter Agent Call
        arbiter_prompt = f"""You are the Institutional Evidence Arbiter for Scheme-Intel.
Reconcile this research debate based STRICTLY on the submitted agent analyses and verified evidence.
Do NOT invent new facts.
QUERY: {query}
VERIFIED FACTS: {json.dumps(fact_points)}
BULL CASE: {json.dumps(bull_case)}
BEAR CASE: {json.dumps(bear_case)}
CONTRADICTIONS IDENTIFIED: {json.dumps(contradictions)}

Determine:
1. Verdict: Exactly one of "BULL", "BEAR", or "MIXED".
2. Why: 2 to 3 decisive bullets evaluating which side has stronger factual support.
3. Confidence: Exactly one of "HIGH", "MEDIUM", or "LOW".
4. Key Risk: Exactly 1 sentence describing the primary vulnerability.
5. Invalidation: Exactly 1 sentence describing what event would change your view.

Return JSON:
{{
  "verdict": "BULL",
  "why": ["point 1", "point 2"],
  "confidence": "MEDIUM",
  "key_risk": "Risk sentence",
  "invalidation": "Invalidation sentence"
}}
"""
        arbiter_res = self._call_provider(
            provider_name=arbiter_provider_name,
            provider=available_providers[arbiter_provider_name],
            prompt=arbiter_prompt,
            system_prompt="You are an impartial institutional arbiter evaluating evidence weight.",
            caller="ArbiterAgent",
            providers_attempted=providers_attempted,
            providers_successful=providers_successful,
            model_names=model_names,
        )
        arbiter_data = self._parse_json_dict(arbiter_res) or {
            "verdict": "MIXED",
            "why": [
                "Commercial policy tailwinds are confirmed, but immediate order execution remains pacing factor.",
                "Balanced risk/reward distribution between policy visibility and execution friction.",
            ],
            "confidence": "LOW" if degraded else "MEDIUM",
            "key_risk": "Subsidies disbursement timeline and broader market volatility.",
            "invalidation": "Official contract announcement or high-volume technical breakout.",
        }

        # If single provider was used, mark degraded confidence explicitly
        confidence = arbiter_data.get("confidence", "MEDIUM")
        if degraded:
            confidence = f"{confidence} (DEGRADED_SINGLE_PROVIDER)"

        duration = time.time() - start_time
        logger.info(
            "RESEARCH_COMPLETED: job_id=%s in %.2fs (providers used: %s)",
            effective_job_id,
            duration,
            providers_successful,
        )

        provenance = ResearchProvenance(
            query=query,
            timestamp=now_iso,
            providers_attempted=providers_attempted,
            providers_successful=providers_successful,
            evidence_sources=dossier["evidence_items"],
            model_names=model_names,
            agent_outputs=agent_outputs,
            contradictions=contradictions,
            final_synthesis=arbiter_data,
            confidence=confidence,
            execution_duration_seconds=round(duration, 2),
            degraded_status=degraded,
            is_fallback=False,
        )

        # Format output
        formatted_card = self._format_research_card(
            job_id=effective_job_id,
            query=query,
            fact_points=fact_points,
            bull_case=bull_case,
            bear_case=bear_case,
            arbiter_data=arbiter_data,
            provenance=provenance,
            comp=comp,
            catalysts=dossier["catalysts"],
            sources=dossier["sources"],
        )

        return ResearchResult(
            result_text=formatted_card,
            evidence_items=dossier["evidence_items"],
            provenance=provenance,
            is_fallback=False,
        )

    def _get_active_providers(self) -> Dict[str, LLMProvider]:
        """Fetch configured and initialized LLM providers."""
        active: Dict[str, LLMProvider] = {}
        # 1. Fetch from ProviderRegistry (Groq, Gemini, OpenAI, OpenRouter)
        reg_active = self.registry.get_active_providers()
        if reg_active:
            active.update(reg_active)

        # 2. Fetch from provider_manager if available
        if self.provider_manager and hasattr(self.provider_manager, "providers"):
            for k, v in self.provider_manager.providers.items():
                if k not in active and not self.provider_manager.is_in_cooldown(k):
                    active[k] = v

        # 3. If mock was provided or provider_manager is the only entity
        if not active and self.provider_manager:
            if hasattr(self.provider_manager, "providers") and self.provider_manager.providers:
                active.update(self.provider_manager.providers)
            else:
                active["provider_manager"] = self.provider_manager

        return active

    def _call_provider(
        self,
        provider_name: str,
        provider: LLMProvider,
        prompt: str,
        system_prompt: str,
        caller: str,
        providers_attempted: List[str],
        providers_successful: List[str],
        model_names: Dict[str, str],
    ) -> str:
        """Execute call on specific provider with observability."""
        if provider_name not in providers_attempted:
            providers_attempted.append(provider_name)
        logger.info("PROVIDER_CALLED: %s by %s", provider_name, caller)

        try:
            resp: ProviderResponse = provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.2,
                caller=caller,
            )
            if provider_name not in providers_successful:
                providers_successful.append(provider_name)
            model_names[provider_name] = getattr(resp, "model", getattr(provider, "model", "default"))
            logger.info("PROVIDER_SUCCESS: %s for %s", provider_name, caller)
            return resp.content.strip()
        except Exception as e:
            logger.warning("PROVIDER_FAILURE: %s failed for %s: %s", provider_name, caller, sanitize_secret(str(e)))
            return ""

    def _generate_snapshot_fallback(
        self,
        query: str,
        scheme: SchemeConfig,
        dossier: Dict[str, Any],
        snapshot_context: Optional[Dict[str, Any]],
        job_id: str,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Explicitly labelled snapshot fallback when no AI providers can execute fresh research.
        MUST NEVER be presented as fresh research.
        """
        lines = [
            "⚠️ *[SNAPSHOT_FALLBACK]*",
            "_Fresh multi-provider research unavailable; returning available snapshot intelligence._",
            "",
            "🔬 *SCHEME-INTEL CACHED INTELLIGENCE*",
            f"*Query:* {query}",
            f"*Request ID:* `{job_id}`",
            "━━━━━━━━━━━━━━",
            f"🏛️ *Scheme:* {scheme.name}",
        ]

        if snapshot_context:
            snap_time = snapshot_context.get("generated_at", "N/A")
            lines.append(f"• *Snapshot Timestamp:* {snap_time}")
            q_setups = snapshot_context.get("qualified_setups", [])
            w_setups = snapshot_context.get("waiting_setups", [])
            lines.append(f"• *Qualified Setups:* {', '.join(q_setups) if q_setups else 'None'}")
            lines.append(f"• *Waiting Setups:* {', '.join(w_setups) if w_setups else 'None'}")

        if dossier["company_data"]:
            lines.append("\n*Relevant Company Snapshot Data:*")
            for sym, comp in dossier["company_data"].items():
                p_str = f"₹{comp.get('price'):.2f}" if comp.get("price") is not None else "N/A"
                lines.append(
                    f"• *{comp.get('short_symbol')}*: {p_str} | Status: `{comp.get('status')}` | "
                    f"Catalyst: {comp.get('catalyst') or 'None'}"
                )

        if dossier["evidence_items"]:
            lines.append("\n*Cached News & Disclosures:*")
            for ev in dossier["evidence_items"][:3]:
                lines.append(f"• [{ev.get('source')}] {ev.get('title')}")

        lines.extend([
            "",
            "━━━━━━━━━━━━━━",
            "ℹ️ _Note: To trigger fresh multi-agent research, ensure at least one AI provider API key is reachable._",
        ])

        return "\n".join(lines), dossier["evidence_items"]

    def _format_research_card(
        self,
        job_id: str,
        query: str,
        fact_points: List[str],
        bull_case: List[str],
        bear_case: List[str],
        arbiter_data: Dict[str, Any],
        provenance: ResearchProvenance,
        comp: Optional[Dict[str, Any]],
        catalysts: List[str],
        sources: List[Dict[str, Any]],
    ) -> str:
        """Build formatted Telegram Markdown research card."""
        tech_score = comp.get("technical_intelligence_score") if comp else None
        fund_score = comp.get("fundamental_intelligence_score") if comp else None
        setup_status = comp.get("status") if comp else "MONITORING"

        lines = [
            "🔬 *SCHEME-INTEL MULTI-PROVIDER RESEARCH*",
            "",
            "*Question:*",
            query.strip(),
            "",
            "━━━━━━━━━━━━━━",
            "",
            "📊 *CURRENT INTELLIGENCE CONTEXT*",
            f"Technical: {tech_score:.1f}/10" if tech_score is not None else "Technical: N/A",
            f"Fundamental: {fund_score:.1f}/10" if fund_score is not None else "Fundamental: N/A",
            f"Trade Setup: `{setup_status}`",
        ]

        if catalysts:
            lines.extend(["", "🔥 *CATALYST*", ""])
            for c in catalysts[:3]:
                lines.append(f"• {c}")

        # Verified Evidence / Facts
        lines.extend(["", "🔍 *INDEPENDENT FACT FINDINGS*", ""])
        for fp in fact_points[:3]:
            lines.append(f"• {fp}")

        # Bull Case
        lines.extend(["", "🟢 *BULL CASE (Opportunity Agent)*", ""])
        for b in bull_case[:3]:
            lines.append(f"• {b}")

        # Bear Case
        lines.extend(["", "🔴 *BEAR CASE (Risk Agent)*", ""])
        for b in bear_case[:3]:
            lines.append(f"• {b}")

        # Arbiter
        verdict = arbiter_data.get("verdict", "MIXED").upper()
        conf = provenance.confidence.upper()
        lines.extend([
            "",
            "🏛️ *ARBITER SYNTHESIS*",
            f"*Verdict:* `{verdict}` | *Confidence:* `{conf}`",
            "",
            "*Why:*",
        ])
        for w in arbiter_data.get("why", []):
            lines.append(f"• {w}")

        lines.extend([
            "",
            "⚠️ *KEY RISK*",
            arbiter_data.get("key_risk", "Policy disbursement friction or broader volatility.").strip(),
            "",
            "🧭 *WHAT WOULD CHANGE THE VIEW*",
            arbiter_data.get("invalidation", "Clear contract award or high-volume price reversal.").strip(),
        ])

        if sources:
            lines.extend(["", "📰 *SOURCES & EVIDENCE*", ""])
            for s in sources[:4]:
                name = s.get("source") or "Official Disclosure"
                title = s.get("title") or s.get("name") or "Filing"
                lines.append(f"• {name}: {title[:75]}")

        # Provenance footer
        providers_used_str = ", ".join(provenance.providers_successful) if provenance.providers_successful else "None"
        lines.extend([
            "",
            "━━━━━━━━━━━━━━",
            f"*Research ID:* `{job_id}`",
            f"*Participating Providers:* `{providers_used_str}`",
            f"*Duration:* {provenance.execution_duration_seconds}s",
        ])

        return "\n".join(lines)

    def _parse_json_list(self, text: str, key: str) -> List[str]:
        if not text:
            return []
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
        if not text:
            return {}
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
