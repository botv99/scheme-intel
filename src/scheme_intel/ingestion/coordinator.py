"""
Scheme Ingestion Coordinator (Stage 4).
Orchestrates multi-scheme data collection while enforcing strict boundary isolation.
Gobardhan sources produce strictly Gobardhan events; Samudra sources produce strictly Samudra events.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import requests

from .models import NormalizedSchemeEvent, SchemeIngestionBatch
from .adapters.base import SourceHealthRecord
from ..schemes.registry import SchemeRegistry
from ..schemes.models import SchemeConfig, SchemeSource
from ..sources import fetch_rss, scan_page
from ..logger import get_logger

logger = get_logger(__name__)


class SchemeBoundaryViolationError(ValueError):
    """Raised when an event from one scheme attempts to cross into another scheme."""
    pass


class SchemeIngestionCoordinator:
    """Coordinates scheme-isolated ingestion across registered source registries."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self._seen_event_hashes: Set[str] = set()

    def generate_event_id(self, scheme_id: str, source_id: str, title: str, published_at: Optional[str] = None) -> str:
        """Deterministically compute idempotent event ID."""
        raw = f"{scheme_id}:{source_id}:{title}:{(published_at or '')[:10]}"
        return f"EVT-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"

    def ingest_event(self, event: NormalizedSchemeEvent, target_scheme_id: str) -> None:
        """
        Ingest a single event into a target scheme verifying boundary isolation.
        Raises SchemeBoundaryViolationError if event.scheme_id != target_scheme_id.
        """
        norm_target = target_scheme_id.strip().lower()
        norm_event_scheme = event.scheme_id.strip().lower()
        if norm_event_scheme != norm_target:
            raise SchemeBoundaryViolationError(
                f"Scheme boundary violation: Event scheme '{norm_event_scheme}' does not match target scheme '{norm_target}'."
            )

    def ingest_scheme(
        self,
        scheme_id: str,
        run_id: Optional[str] = None,
        mock_source_data: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> SchemeIngestionBatch:
        """
        Execute isolated ingestion for a single scheme.
        Fails safely per source without stopping the entire run.
        """
        norm_scheme = scheme_id.strip().lower()
        effective_run_id = run_id or f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        now_utc = datetime.now(timezone.utc).isoformat()

        scheme = SchemeRegistry.get(norm_scheme)
        if not scheme:
            logger.error("[INGESTION] Scheme '%s' not registered.", norm_scheme)
            return SchemeIngestionBatch(
                scheme_id=norm_scheme,
                run_id=effective_run_id,
                timestamp=now_utc,
                source_health={"registry": "SCHEME_NOT_FOUND"},
                errors=[{"source": "registry", "error": f"Scheme '{norm_scheme}' not found"}],
            )

        events: List[NormalizedSchemeEvent] = []
        source_health: Dict[str, str] = {}
        errors: List[Dict[str, Any]] = []
        source_health_records: List[SourceHealthRecord] = []
        raw_documents: List[Dict[str, Any]] = []

        logger.info("[INGESTION] Starting isolated ingestion for scheme '%s' (sources=%d)", norm_scheme, len(scheme.sources))

        for src in scheme.sources:
            if not src.enabled:
                source_health[src.id] = "DISABLED"
                source_health_records.append(SourceHealthRecord(source_id=src.id, status="DISABLED"))
                continue

            # Support deterministic test mock data if provided
            if mock_source_data and src.id in mock_source_data:
                source_health[src.id] = "OK"
                source_health_records.append(SourceHealthRecord(source_id=src.id, status="OK", event_count=len(mock_source_data[src.id])))
                raw_documents.extend(mock_source_data[src.id])
                for item in mock_source_data[src.id]:
                    # Hard boundary check: enforce scheme identity
                    if item.get("scheme_id") and item.get("scheme_id").lower() != norm_scheme:
                        raise SchemeBoundaryViolationError(
                            f"Cross-scheme contamination: item with scheme '{item.get('scheme_id')}' in {norm_scheme} ingestion"
                        )
                    evt_id = item.get("event_id") or self.generate_event_id(norm_scheme, src.id, item.get("title", ""))
                    events.append(NormalizedSchemeEvent(
                        event_id=evt_id,
                        scheme_id=norm_scheme,
                        source_id=src.id,
                        event_type=item.get("event_type", "SCHEME_POLICY"),
                        title=item.get("title", ""),
                        content=item.get("content", item.get("title", "")),
                        summary=item.get("summary", ""),
                        published_at=item.get("published_at", now_utc),
                        retrieved_at=now_utc,
                        entities=item.get("entities", []),
                        evidence=item.get("evidence", [{"source": src.name, "url": src.url}]),
                        importance=item.get("importance", "MEDIUM"),
                        confidence=item.get("confidence", 1.0),
                        url=item.get("url", src.url),
                        external_id=item.get("external_id"),
                        companies=item.get("companies", []),
                        projects=item.get("projects", []),
                        contracts=item.get("contracts", []),
                        relevance_reason=item.get("relevance_reason"),
                        water_depth=item.get("water_depth"),
                    ))
                continue

            # Check for specialized real SourceAdapter
            from .adapters import AdapterRegistry
            adapter = AdapterRegistry.get_adapter(norm_scheme, src.id)
            if adapter:
                try:
                    adapter_events, health = adapter.ingest(custom_url=src.url)
                    source_health[src.id] = health.status
                    source_health_records.append(health)
                    for raw_rec in getattr(adapter, "last_raw_records", []) or []:
                        raw_documents.append({
                            "source_id": src.id,
                            "title": getattr(raw_rec, "title", ""),
                            "url": getattr(raw_rec, "url", ""),
                            "content": getattr(raw_rec, "content", ""),
                            "summary": getattr(raw_rec, "summary", None),
                            "published_at": getattr(raw_rec, "published_at", None),
                            "external_id": getattr(raw_rec, "external_id", None),
                            "raw_metadata": getattr(raw_rec, "raw_metadata", {}),
                        })
                    for evt in adapter_events:
                        self.ingest_event(evt, target_scheme_id=norm_scheme)
                        if evt.event_id in self._seen_event_hashes:
                            continue
                        self._seen_event_hashes.add(evt.event_id)
                        events.append(evt)
                    if health.status in ("FAILED", "BLOCKED") and health.reason:
                        errors.append({"source_id": src.id, "error": health.reason})
                        # Activate fallbacks if Samudra source is blocked/failed
                        if norm_scheme == "samudra_manthan":
                            from ..schemes.samudra_manthan.redundancy import get_fallback_sources_for_source
                            fallbacks = get_fallback_sources_for_source(src.id)
                            if fallbacks:
                                health.fallback = f"Active fallbacks: {', '.join(f.source_id for f in fallbacks)}"
                                logger.info(
                                    "[INGESTION] Source '%s' %s. Fallback group activated: %s",
                                    src.id, health.status, health.fallback
                                )
                                # Dynamically execute fallback adapters if not part of scheme source list
                                configured_source_ids = {s.id for s in scheme.sources}
                                for fb in fallbacks:
                                    if fb.source_id not in configured_source_ids and fb.enabled:
                                        fb_adapter = AdapterRegistry.get_adapter(norm_scheme, fb.source_id)
                                        if fb_adapter:
                                            try:
                                                fb_events, fb_health = fb_adapter.ingest(custom_url=fb.url)
                                                source_health[fb.source_id] = fb_health.status
                                                source_health_records.append(fb_health)
                                                for fb_evt in fb_events:
                                                    self.ingest_event(fb_evt, target_scheme_id=norm_scheme)
                                                    if fb_evt.event_id in self._seen_event_hashes:
                                                        continue
                                                    self._seen_event_hashes.add(fb_evt.event_id)
                                                    events.append(fb_evt)
                                            except Exception as fb_err:
                                                logger.warning("[INGESTION] Fallback adapter '%s' failed: %s", fb.source_id, fb_err)
                except Exception as e:
                    logger.warning("[INGESTION] Adapter '%s' failed: %s", src.id, e)
                    fb_note = None
                    if norm_scheme == "samudra_manthan":
                        from ..schemes.samudra_manthan.redundancy import get_fallback_sources_for_source
                        fallbacks = get_fallback_sources_for_source(src.id)
                        if fallbacks:
                            fb_note = f"Active fallbacks: {', '.join(f.source_id for f in fallbacks)}"
                    source_health[src.id] = "DEGRADED"
                    source_health_records.append(SourceHealthRecord(source_id=src.id, status="DEGRADED", reason=str(e)[:200], fallback=fb_note))
                    errors.append({"source_id": src.id, "error": str(e)[:200]})
                continue

            # Fallback network adapter execution (for non-adaptered schemes/sources)
            try:
                if src.type == "rss":
                    articles = fetch_rss(src.name, src.url, timeout=self.timeout)
                    source_health[src.id] = "OK"
                    source_health_records.append(SourceHealthRecord(source_id=src.id, status="OK", event_count=len(articles[:10])))
                    for art in articles[:10]:
                        raw_documents.append({"source_id": src.id, "title": art.title, "url": art.url})
                        evt_id = self.generate_event_id(norm_scheme, src.id, art.title, art.published_at.isoformat() if art.published_at else None)
                        if evt_id in self._seen_event_hashes:
                            continue
                        self._seen_event_hashes.add(evt_id)
                        events.append(NormalizedSchemeEvent(
                            event_id=evt_id,
                            scheme_id=norm_scheme,
                            source_id=src.id,
                            event_type="SCHEME_POLICY",
                            title=art.title,
                            content=art.summary or art.title,
                            summary=art.summary,
                            published_at=art.published_at.isoformat() if art.published_at else now_utc,
                            retrieved_at=now_utc,
                            entities=[stock.name for stock in scheme.watchlist if stock.name.lower() in art.title.lower()],
                            evidence=[{"source": src.name, "url": art.url}],
                            importance="HIGH" if any(k in art.title.lower() for k in scheme.keywords[:5]) else "MEDIUM",
                            confidence=0.90,
                            url=art.url,
                        ))
                else:
                    # HTML / Tender / Filing fallback ping
                    resp = requests.get(src.url, timeout=self.timeout, headers={"User-Agent": "scheme-intel/0.4"}, verify=False)
                    if resp.status_code == 200:
                        source_health[src.id] = "OK"
                        source_health_records.append(SourceHealthRecord(source_id=src.id, status="OK"))
                        raw_documents.append({"source_id": src.id, "url": src.url, "content": resp.text[:500]})
                    else:
                        source_health[src.id] = f"HTTP_{resp.status_code}"
                        source_health_records.append(SourceHealthRecord(source_id=src.id, status=f"HTTP_{resp.status_code}"))
            except Exception as e:
                logger.warning("[INGESTION] Source '%s' (%s) degraded/failed: %s", src.id, src.name, e)
                source_health[src.id] = "DEGRADED"
                source_health_records.append(SourceHealthRecord(source_id=src.id, status="DEGRADED", reason=str(e)[:200]))
                errors.append({"source_id": src.id, "error": str(e)[:200]})

        # Cross-Source Corroboration & Deduplication for Samudra Manthan
        if norm_scheme == "samudra_manthan" and events:
            from .corroboration import CrossSourceCorroborator
            pre_count = len(events)
            events = CrossSourceCorroborator.corroborate_and_deduplicate(events)
            logger.info(
                "[INGESTION] Cross-source corroboration complete for '%s': %d raw -> %d canonical events",
                norm_scheme,
                pre_count,
                len(events),
            )

        batch = SchemeIngestionBatch(
            scheme_id=norm_scheme,
            run_id=effective_run_id,
            timestamp=now_utc,
            events=events,
            source_health=source_health,
            errors=errors,
            source_health_records=source_health_records,
            raw_documents=raw_documents,
        )
        logger.info(
            "[INGESTION] Completed scheme '%s': %d events, %d errors, status=%s",
            norm_scheme,
            len(events),
            len(errors),
            "OK" if not errors else "PARTIAL",
        )
        return batch

    def run_ingestion(
        self,
        scheme_id: str,
        run_id: Optional[str] = None,
        mock_source_data: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> SchemeIngestionBatch:
        """Alias for ingest_scheme."""
        return self.ingest_scheme(scheme_id=scheme_id, run_id=run_id, mock_source_data=mock_source_data)

    def ingest_all_active_schemes(
        self,
        run_id: Optional[str] = None,
        mock_data_by_scheme: Optional[Dict[str, Dict[str, List[Dict[str, Any]]]]] = None,
    ) -> Dict[str, SchemeIngestionBatch]:
        """Ingest all registered active schemes concurrently or sequentially without cross-leakage."""
        results: Dict[str, SchemeIngestionBatch] = {}
        for scheme in SchemeRegistry.get_active_schemes():
            scheme_mock = (mock_data_by_scheme or {}).get(scheme.id)
            results[scheme.id] = self.ingest_scheme(
                scheme_id=scheme.id,
                run_id=run_id,
                mock_source_data=scheme_mock,
            )
        return results
