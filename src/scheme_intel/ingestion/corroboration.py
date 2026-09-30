"""
Cross-Source Corroboration, Deduplication, and Evidence Confidence Engine (Stage 4E).
Implements:
1. Canonical event identification across multi-tier sources (Official, Exchange, News, Specialist).
2. Multi-source evidence aggregation: merges multiple reports of the same event into a single canonical event.
3. Transparent evidence confidence calculation (authority tier base + multi-source corroboration boost).
4. Duplicate news suppression (one canonical event with multiple evidence references).
5. Legacy and historical date handling (preserves original published_at, tags historical events).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import NormalizedSchemeEvent
from ..logger import get_logger

logger = get_logger(__name__)

AUTHORITY_PRIORITY: Dict[str, int] = {
    "official": 1,
    "exchange": 2,
    "news": 3,
    "specialist": 4,
    "legacy": 5,
}


class CrossSourceCorroborator:
    """
    Corroborates and deduplicates NormalizedSchemeEvents across multiple independent sources.
    Merges duplicate reports into a single high-confidence event backed by comprehensive evidence.
    """

    @classmethod
    def extract_canonical_tokens(cls, event: NormalizedSchemeEvent) -> Tuple[str, str, str]:
        """
        Derives canonical identity tokens: (primary_entity, subject_key, date_bucket).
        Used to detect when multiple sources report the same underlying event.
        """
        title = event.title.upper()
        content = (event.content or "").upper()
        combined = f"{title} {content}"

        # 1. Primary Entity Extraction
        entities = event.companies or event.entities
        if entities:
            primary_entity = re.sub(r"[^A-Z0-9]", "", entities[0].upper())
        elif "ONGC" in combined:
            primary_entity = "ONGC"
        elif "OIL INDIA" in combined:
            primary_entity = "OIL_INDIA"
        elif "RELIANCE" in combined or "RIL" in combined:
            primary_entity = "RELIANCE"
        elif "VEDANTA" in combined or "CAIRN" in combined:
            primary_entity = "VEDANTA"
        elif "DGH" in combined:
            primary_entity = "DGH"
        elif "MOPNG" in combined or "MINISTRY OF PETROLEUM" in combined:
            primary_entity = "MOPNG"
        else:
            primary_entity = "UPSTREAM_SECTOR"

        # 2. Subject Key Extraction
        # Look for contract numbers or tender IDs
        contracts = event.contracts
        if contracts:
            subject_key = re.sub(r"[^A-Z0-9]", "", contracts[0].upper())[:20]
        else:
            # Match project or major theme keywords
            themes = [
                ("OALP_ROUND", r"OALP\s*(?:ROUND|BIDDING|\bX\b|\bIX\b|\b10\b|\b9\b)"),
                ("KG_DWN_98_2", r"KG-DWN-98/2|98/2"),
                ("KG_D6", r"KG-D6|R-CLUSTER|MJ\s*FIELD"),
                ("ANDAMAN_EXPLORATION", r"ANDAMAN"),
                ("MUMBAI_HIGH", r"MUMBAI\s*HIGH"),
                ("SEISMIC_SURVEY", r"SEISMIC\s*(?:SURVEY|OBN|2D|3D)"),
                ("RIG_CHARTER", r"(?:RIG|DRILLSHIP|JACKUP)\s*(?:CHARTER|HIRE|CONTRACT)"),
                ("DEEPWATER_DISCOVERY", r"(?:DEEPWATER|GAS|OIL)\s*DISCOVERY"),
                ("SUBSEA_EPC", r"SUBSEA|UMBILICAL|FLOWLINE"),
            ]
            subject_key = "GENERAL_UPDATE"
            for t_name, pattern in themes:
                if re.search(pattern, combined):
                    subject_key = t_name
                    break

            if subject_key == "GENERAL_UPDATE":
                # Fall back to cleaned 3 significant words from title
                words = [w for w in re.findall(r"\b[A-Z]{4,}\b", title) if w not in ("INDIA", "INDIA'S", "OFFSHORE", "EXPLORATION", "ENERGY")]
                subject_key = "_".join(words[:3]) or "EVENT"

        # 3. Date Bucket (Group events within 5-day windows)
        date_str = (event.published_at or "")[:10]
        try:
            dt = datetime.fromisoformat(date_str)
            # 5-day bucket
            day_bucket = dt.timetuple().tm_yday // 5
            date_bucket = f"{dt.year}-B{day_bucket:02d}"
        except Exception:
            date_bucket = date_str[:7] or "NO_DATE"

        return primary_entity, subject_key, date_bucket

    @classmethod
    def generate_canonical_hash(cls, scheme_id: str, primary_entity: str, subject_key: str, date_bucket: str) -> str:
        """Deterministically generates a canonical event ID."""
        raw = f"{scheme_id}:{primary_entity}:{subject_key}:{date_bucket}"
        return f"CANON-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"

    @classmethod
    def merge_events(cls, events_group: List[NormalizedSchemeEvent]) -> NormalizedSchemeEvent:
        """
        Merge a cluster of corroborating events into a single canonical event.
        - Selects the best title and content from the highest authority source.
        - Merges distinct evidence records.
        - Boosts confidence based on multi-source corroboration.
        - Consolidates entities, companies, projects, contracts.
        """
        if len(events_group) == 1:
            single = events_group[0]
            is_legacy = any(ev.get("is_legacy") for ev in single.evidence) or "legacy" in single.source_id.lower()
            is_old = False
            try:
                pub_dt = datetime.fromisoformat(single.published_at[:10])
                now_dt = datetime.now(timezone.utc)
                if (now_dt.date() - pub_dt.date()).days > 180:
                    is_old = True
            except Exception:
                pass
            if is_legacy or is_old:
                single.event_type = "HISTORICAL_ARCHIVE"
            return single

        # Sort by authority level (Official > Exchange > News > Specialist > Legacy)
        def _get_authority(ev: NormalizedSchemeEvent) -> int:
            for ev_item in ev.evidence:
                auth = ev_item.get("authority_level")
                if auth:
                    return int(auth)
                src_type = str(ev_item.get("source_type", "")).lower()
                if src_type in AUTHORITY_PRIORITY:
                    return AUTHORITY_PRIORITY[src_type]
            if "filing" in ev.source_id:
                return 2
            if any(k in ev.source_id for k in ("news", "reuters", "et_", "mint", "business_standard")):
                return 3
            if "offshore_technology" in ev.source_id:
                return 4
            if "legacy" in ev.source_id:
                return 5
            return 1

        sorted_events = sorted(events_group, key=_get_authority)
        lead_event = sorted_events[0]

        # Union entities, companies, projects, contracts
        companies: Set[str] = set()
        projects: Set[str] = set()
        contracts: Set[str] = set()
        entities: Set[str] = set()
        evidence_list: List[Dict[str, Any]] = []
        seen_evidence_urls: Set[str] = set()
        distinct_sources: Set[str] = set()

        is_all_legacy = True
        highest_importance = "LOW"
        importance_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

        for ev in sorted_events:
            for c in ev.companies:
                companies.add(c)
            for p in ev.projects:
                projects.add(p)
            for ct in ev.contracts:
                contracts.add(ct)
            for e in ev.entities:
                entities.add(e)

            distinct_sources.add(ev.source_id)

            if importance_rank.get(ev.importance.upper(), 1) > importance_rank.get(highest_importance, 1):
                highest_importance = ev.importance.upper()

            for ev_record in ev.evidence:
                if not ev_record.get("is_legacy"):
                    is_all_legacy = False
                url_key = ev_record.get("url") or ev_record.get("source")
                if url_key and url_key not in seen_evidence_urls:
                    seen_evidence_urls.add(url_key)
                    evidence_list.append(ev_record)

        # Multi-source corroboration boost
        # Base confidence from lead event + 0.05 for each independent corroborating source (up to 0.99)
        num_corroborating = len(distinct_sources)
        base_conf = lead_event.confidence
        corroboration_bonus = min(0.12, 0.05 * (num_corroborating - 1))
        boosted_confidence = min(0.99, round(base_conf + corroboration_bonus, 2))

        # Check if historical
        is_historical = False
        try:
            pub_dt = datetime.fromisoformat(lead_event.published_at[:10])
            now_dt = datetime.now(timezone.utc)
            if (now_dt.date() - pub_dt.date()).days > 180:
                is_historical = True
        except Exception:
            pass

        return NormalizedSchemeEvent(
            event_id=lead_event.event_id,
            scheme_id=lead_event.scheme_id,
            source_id=lead_event.source_id,
            event_type="HISTORICAL_ARCHIVE" if (is_all_legacy or is_historical) else lead_event.event_type,
            title=lead_event.title,
            content=lead_event.content,
            summary=lead_event.summary,
            published_at=lead_event.published_at,
            retrieved_at=lead_event.retrieved_at,
            entities=sorted(list(entities)),
            evidence=evidence_list,
            importance=highest_importance,
            confidence=boosted_confidence,
            url=lead_event.url,
            external_id=lead_event.external_id,
            companies=sorted(list(companies)),
            projects=sorted(list(projects)),
            contracts=sorted(list(contracts)),
            relevance_reason=lead_event.relevance_reason,
            water_depth=lead_event.water_depth,
        )

    @classmethod
    def corroborate_and_deduplicate(
        cls,
        events: List[NormalizedSchemeEvent],
    ) -> List[NormalizedSchemeEvent]:
        """
        Groups events by canonical identity tokens and merges duplicates into corroborated events.
        Ensures 0 duplicate news stories while capturing all corroborating sources.
        """
        if not events:
            return []

        clusters: Dict[str, List[NormalizedSchemeEvent]] = {}
        for ev in events:
            p_entity, s_key, d_bucket = cls.extract_canonical_tokens(ev)
            canon_hash = cls.generate_canonical_hash(ev.scheme_id, p_entity, s_key, d_bucket)
            clusters.setdefault(canon_hash, []).append(ev)

        corroborated_events: List[NormalizedSchemeEvent] = []
        for canon_hash, group in clusters.items():
            merged = cls.merge_events(group)
            # Reassign canonical event id if merged across multiple sources
            if len(group) > 1:
                merged.event_id = canon_hash
                logger.info(
                    "[CORROBORATION] Merged %d sources for event '%s' (confidence: %.2f)",
                    len(group),
                    merged.title[:50],
                    merged.confidence,
                )
            corroborated_events.append(merged)

        return corroborated_events
