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

        logger.info("[INGESTION] Starting isolated ingestion for scheme '%s' (sources=%d)", norm_scheme, len(scheme.sources))

        for src in scheme.sources:
            if not src.enabled:
                source_health[src.id] = "DISABLED"
                continue

            # Support deterministic test mock data if provided
            if mock_source_data and src.id in mock_source_data:
                source_health[src.id] = "OK"
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
                    ))
                continue

            # Live network adapter execution
            try:
                if src.type == "rss":
                    articles = fetch_rss(src.name, src.url, timeout=self.timeout)
                    source_health[src.id] = "OK"
                    for art in articles[:10]:
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
                    # HTML / Tender / Filing adapter
                    # Safe check with short timeout
                    resp = requests.get(src.url, timeout=self.timeout, headers={"User-Agent": "scheme-intel/0.4"})
                    if resp.status_code == 200:
                        source_health[src.id] = "OK"
                    else:
                        source_health[src.id] = f"HTTP_{resp.status_code}"
            except Exception as e:
                logger.warning("[INGESTION] Source '%s' (%s) degraded/failed: %s", src.id, src.name, e)
                source_health[src.id] = "DEGRADED"
                errors.append({"source_id": src.id, "error": str(e)[:200]})

        batch = SchemeIngestionBatch(
            scheme_id=norm_scheme,
            run_id=effective_run_id,
            timestamp=now_utc,
            events=events,
            source_health=source_health,
            errors=errors,
        )
        logger.info(
            "[INGESTION] Completed scheme '%s': %d events, %d errors, status=%s",
            norm_scheme,
            len(events),
            len(errors),
            "OK" if not errors else "PARTIAL",
        )
        return batch

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
