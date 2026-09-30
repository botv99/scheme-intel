"""
Base Source Adapter Architecture and Health Contracts (Stage 4B).
Defines standard interfaces for fetching, parsing, normalizing, deduplicating,
and health monitoring across multi-scheme data sources.
"""
from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from ..models import NormalizedSchemeEvent
from ...logger import get_logger

logger = get_logger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class SourceHealthRecord:
    """Detailed health, parser status, and diagnostics for an individual source."""
    source_id: str
    status: str = "OK"                            # "OK", "PARTIAL", "FAILED", "BLOCKED", "STALE", "DISABLED"
    last_attempt: Optional[str] = None           # ISO 8601 UTC
    last_success: Optional[str] = None           # ISO 8601 UTC
    last_event: Optional[str] = None             # Timestamp of most recent event
    event_count: int = 0
    failure_count: int = 0
    parser_status: str = "PENDING"               # "OK", "NO_ITEMS", "PARSE_ERROR", "FILTERED_EMPTY", "BLOCKED"
    reason: Optional[str] = None                 # Diagnostic message or block reason
    fallback: Optional[str] = None               # Fallback mechanism if blocked/degraded
    latency_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "last_attempt": self.last_attempt,
            "last_success": self.last_success,
            "last_event": self.last_event,
            "event_count": self.event_count,
            "failure_count": self.failure_count,
            "parser_status": self.parser_status,
            "reason": self.reason,
            "fallback": self.fallback,
            "latency_ms": self.latency_ms,
        }

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass
class FetchResult:
    """Network fetch result from HTTP / RSS / API endpoint."""
    status_code: Optional[int] = None
    content: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    latency_ms: int = 0
    error: Optional[str] = None
    is_blocked: bool = False
    block_reason: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status_code == 200 and not self.is_blocked and bool(self.content)


@dataclass
class RawExtractedRecord:
    """Intermediate extracted record before scheme-specific normalization."""
    title: str
    url: str
    content: str = ""
    summary: Optional[str] = None
    published_at: Optional[str] = None
    external_id: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


class BaseSourceAdapter(ABC):
    """
    Standard contract for all scheme source adapters.
    Pipeline:
        FETCH -> PARSE -> NORMALIZE -> VALIDATE -> DEDUPLICATE
    """

    def __init__(
        self,
        source_id: str,
        scheme_id: str,
        source_type: str,
        name: str,
        url: str,
        timeout: int = 15,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.source_id = source_id
        self.scheme_id = scheme_id.strip().lower()
        self.source_type = source_type
        self.name = name
        self.url = url
        self.timeout = timeout
        self.headers = headers or {"User-Agent": DEFAULT_USER_AGENT}
        self._seen_ids: Set[str] = set()
        self.last_raw_records: List[RawExtractedRecord] = []

    def generate_event_id(self, external_id: Optional[str], title: str, published_at: Optional[str]) -> str:
        """Deterministic idempotent hash ID for events."""
        key = f"{self.scheme_id}:{self.source_id}:{external_id or ''}:{title[:80]}:{(published_at or '')[:10]}"
        return f"EVT-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"

    def fetch(self, custom_url: Optional[str] = None, session: Optional[requests.Session] = None) -> FetchResult:
        """
        Fetch raw text content from the source URL.
        Detects bot protection (WAF / Cloudflare / Akamai), timeouts, and HTTP errors.
        """
        target_url = custom_url or self.url
        t0 = time.time()
        client = session or requests
        try:
            resp = client.get(
                target_url,
                headers=self.headers,
                timeout=self.timeout,
                verify=False,
            )
            latency = int((time.time() - t0) * 1000)

            # Check for bot mitigation blocks (Akamai, Cloudflare, CAPTCHA)
            if resp.status_code in (403, 429) or any(
                b in resp.text.lower() for b in ["access denied", "attention required! | cloudflare", "cf-browser-verification", "captcha"]
            ):
                return FetchResult(
                    status_code=resp.status_code,
                    content=resp.text,
                    headers=dict(resp.headers),
                    latency_ms=latency,
                    error=f"Bot protection / access denied (HTTP {resp.status_code})",
                    is_blocked=True,
                    block_reason=f"Endpoint protected by WAF/Cloudflare/Akamai (HTTP {resp.status_code})",
                )

            if resp.status_code != 200:
                return FetchResult(
                    status_code=resp.status_code,
                    content=resp.text,
                    headers=dict(resp.headers),
                    latency_ms=latency,
                    error=f"HTTP status {resp.status_code}",
                )

            # Check for client-side SPA with empty body
            if "<app-root></app-root>" in resp.text and len(resp.text) < 50000 and "data-beasties-container" in resp.text:
                return FetchResult(
                    status_code=200,
                    content=resp.text,
                    headers=dict(resp.headers),
                    latency_ms=latency,
                    is_blocked=True,
                    block_reason="Client-side Angular SPA requires JavaScript execution environment",
                )

            return FetchResult(
                status_code=200,
                content=resp.text,
                headers=dict(resp.headers),
                latency_ms=latency,
            )

        except requests.exceptions.Timeout:
            latency = int((time.time() - t0) * 1000)
            return FetchResult(
                status_code=None,
                latency_ms=latency,
                error=f"Timeout after {self.timeout}s connecting to {target_url}",
            )
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            return FetchResult(
                status_code=None,
                latency_ms=latency,
                error=f"Network error: {type(e).__name__} ({str(e)[:100]})",
            )

    @abstractmethod
    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        """Parse raw content (HTML/XML/JSON) into structured records."""
        raise NotImplementedError

    @abstractmethod
    def normalize(self, records: List[RawExtractedRecord]) -> List[NormalizedSchemeEvent]:
        """Normalize parsed records into standard NormalizedSchemeEvent objects."""
        raise NotImplementedError

    @classmethod
    def is_spa_detected(cls, content: str) -> bool:
        """Detect if page is a client-side JavaScript Single Page App (e.g. Angular/React)."""
        if not content:
            return False
        return "<app-root>" in content or "data-beasties-container" in content or 'id="root"></div' in content

    def parse_and_normalize(self, raw_content: str, url: Optional[str] = None) -> List[NormalizedSchemeEvent]:
        """Convenience method: parse raw content and normalize into validated events."""
        if not raw_content:
            return []
        records = self.parse(raw_content)
        events = self.normalize(records)
        return [e for e in events if self.validate(e)]

    def validate(self, event: NormalizedSchemeEvent) -> bool:
        """
        Validate NormalizedSchemeEvent before emission.
        Must have non-empty title, valid scheme_id, and evidence.
        """
        if not event.title or not event.title.strip():
            return False
        if event.scheme_id.lower() != self.scheme_id.lower():
            return False
        if not event.evidence:
            return False
        return True

    def ingest(
        self,
        mock_content: Optional[str] = None,
        custom_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> Tuple[List[NormalizedSchemeEvent], SourceHealthRecord]:
        """
        Execute full end-to-end ingestion cycle for this source:
        FETCH -> PARSE -> NORMALIZE -> VALIDATE -> DEDUPLICATE.
        Never throws unhandled exceptions that break the coordinator run.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        health = SourceHealthRecord(
            source_id=self.source_id,
            last_attempt=now_utc,
        )

        # 1. FETCH
        if mock_content is not None:
            fetch_res = FetchResult(
                status_code=200,
                content=mock_content,
                latency_ms=1,
            )
        else:
            fetch_res = self.fetch(custom_url=custom_url, session=session)

        health.latency_ms = fetch_res.latency_ms

        if fetch_res.is_blocked:
            health.status = "BLOCKED"
            health.parser_status = "BLOCKED"
            health.reason = fetch_res.block_reason
            health.fallback = "Local fixture / archive cache"
            logger.warning("[ADAPTER:%s] Source blocked: %s", self.source_id, health.reason)
            return [], health

        if not fetch_res.is_success:
            health.status = "FAILED"
            health.parser_status = "FETCH_FAILED"
            health.failure_count = 1
            health.reason = fetch_res.error or f"Fetch failed with HTTP {fetch_res.status_code}"
            logger.warning("[ADAPTER:%s] Fetch failure: %s", self.source_id, health.reason)
            return [], health

        health.last_success = now_utc

        # 2. PARSE
        try:
            raw_records = self.parse(fetch_res.content)
            self.last_raw_records = raw_records
        except Exception as e:
            self.last_raw_records = []
            logger.error("[ADAPTER:%s] Parser crashed on content: %s", self.source_id, e)
            health.status = "FAILED"
            health.parser_status = "PARSE_ERROR"
            health.failure_count = 1
            health.reason = f"Parser exception: {str(e)[:150]}"
            return [], health

        if not raw_records:
            health.status = "OK"
            health.parser_status = "NO_ITEMS"
            health.event_count = 0
            health.reason = "Zero raw items extracted from page"
            return [], health

        # 3. NORMALIZE
        try:
            norm_events = self.normalize(raw_records)
        except Exception as e:
            logger.error("[ADAPTER:%s] Normalizer crashed: %s", self.source_id, e)
            health.status = "PARTIAL"
            health.parser_status = "NORMALIZE_ERROR"
            health.reason = f"Normalizer error: {str(e)[:150]}"
            return [], health

        # 4. VALIDATE & DEDUPLICATE
        valid_events: List[NormalizedSchemeEvent] = []
        for evt in norm_events:
            if not self.validate(evt):
                continue
            if evt.event_id in self._seen_ids:
                continue
            self._seen_ids.add(evt.event_id)
            valid_events.append(evt)

        health.event_count = len(valid_events)
        if valid_events:
            health.status = "OK"
            health.parser_status = "OK"
            health.last_event = valid_events[0].published_at or now_utc
        else:
            health.status = "OK"
            health.parser_status = "FILTERED_EMPTY"
            health.reason = f"Parsed {len(raw_records)} items, but 0 met scheme relevance criteria"

        return valid_events, health
