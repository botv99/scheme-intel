"""
Scheme-Isolated Durable Memory Store (Stage 4).
Stores and retrieves event-based durable facts partitioned strictly by scheme_id.
Enforces hard logical isolation: Gobardhan never reads Samudra; Samudra never reads Gobardhan.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "scheme_intel.db"
DEFAULT_MEMORY_DIR = Path(__file__).resolve().parents[3] / "data" / "memory"


class MemoryFact(BaseModel):
    """Event-based durable fact record."""
    event_id: str
    scheme_id: str
    entity: str
    event_text: str
    timestamp: str
    importance: str = "MEDIUM"
    source: str = ""
    confidence: float = 1.0
    status: str = "ACTIVE"


class SchemeMemoryFactStore:
    """Stores and retrieves durable facts isolated strictly per scheme."""

    def __init__(self, db_path: Optional[Path | str] = None, memory_dir: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.memory_dir = Path(memory_dir) if memory_dir else DEFAULT_MEMORY_DIR
        self._lock = threading.Lock()
        self._init_storage()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_storage(self) -> None:
        try:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            conn = self._get_connection()
            try:
                with self._lock:
                    conn.execute("""
                    CREATE TABLE IF NOT EXISTS scheme_memory_events (
                        event_id            TEXT PRIMARY KEY,
                        scheme_id           TEXT NOT NULL,
                        entity              TEXT NOT NULL,
                        event_text          TEXT NOT NULL,
                        timestamp           TEXT NOT NULL,
                        importance          TEXT DEFAULT 'MEDIUM',
                        source              TEXT,
                        confidence          REAL DEFAULT 1.0,
                        status              TEXT DEFAULT 'ACTIVE',
                        created_at          TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_scheme_entity ON scheme_memory_events(scheme_id, entity);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_scheme_time ON scheme_memory_events(scheme_id, timestamp);")
                    conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug("SchemeMemoryFactStore init note: %s", e)

    def record_fact(
        self,
        scheme_id: str,
        entity_or_text: str = "",
        event_text: Optional[str] = None,
        entity: Optional[str] = None,
        timestamp: Optional[str] = None,
        importance: str = "MEDIUM",
        source: str = "",
        confidence: float = 1.0,
        status: str = "ACTIVE",
        source_name: Optional[str] = None,
    ) -> MemoryFact:
        """
        Record a durable fact into the scheme-scoped partition.
        Fails safely if scheme_id is missing.
        """
        norm_scheme = (scheme_id or "").strip().lower()
        if not norm_scheme:
            raise ValueError("scheme_id is mandatory for recording durable memory facts (fail-closed).")

        if entity is not None:
            clean_entity = entity.strip()
            clean_text = (event_text if event_text is not None else entity_or_text).strip()
        elif event_text is None:
            clean_entity = "GLOBAL"
            clean_text = entity_or_text.strip()
        else:
            clean_entity = entity_or_text.strip()
            clean_text = event_text.strip()

        effective_source = source_name or source or ""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        evt_hash = hashlib.sha256(f"{norm_scheme}:{clean_entity.upper()}:{clean_text}".encode("utf-8")).hexdigest()[:16]
        event_id = f"MEM-{norm_scheme[:3].upper()}-{evt_hash}"

        fact = MemoryFact(
            event_id=event_id,
            scheme_id=norm_scheme,
            entity=clean_entity,
            event_text=clean_text,
            timestamp=ts,
            importance=importance,
            source=effective_source,
            confidence=confidence,
            status=status,
        )

        conn = self._get_connection()
        try:
            with self._lock:
                conn.execute("""
                INSERT OR REPLACE INTO scheme_memory_events (
                    event_id, scheme_id, entity, event_text, timestamp, importance, source, confidence, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    fact.event_id,
                    fact.scheme_id,
                    fact.entity,
                    fact.event_text,
                    fact.timestamp,
                    fact.importance,
                    fact.source,
                    fact.confidence,
                    fact.status,
                ))
                conn.commit()
        finally:
            conn.close()

        # Also append to scheme-isolated JSONL disk ledger
        try:
            scheme_dir = self.memory_dir / norm_scheme
            scheme_dir.mkdir(parents=True, exist_ok=True)
            ledger_file = scheme_dir / "events.jsonl"
            with open(ledger_file, "a", encoding="utf-8") as f:
                f.write(fact.model_dump_json() + "\n")
        except Exception as e:
            logger.debug("Failed appending to memory jsonl ledger: %s", e)

        logger.info("[MEMORY] Recorded fact for %s in scheme '%s' (event_id=%s)", clean_entity, norm_scheme, event_id)
        return fact

    def ingest_event(
        self,
        scheme_id: str,
        event_id: str,
        fact_type: str = "event",
        title: str = "",
        content: str = "",
        confidence: float = 1.0,
        importance: str = "MEDIUM",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryFact:
        """Convenience adapter for ingesting NormalizedSchemeEvents into memory facts."""
        entity = "GLOBAL"
        if metadata and metadata.get("companies"):
            entity = metadata["companies"][0]
        text = f"{title}: {content}".strip() if title else content
        return self.record_fact(
            scheme_id=scheme_id,
            entity=entity,
            event_text=text or "event",
            importance=importance,
            confidence=confidence,
            source=fact_type,
        )

    def query_facts(
        self,
        scheme_id: str,
        entity: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryFact]:
        """
        Retrieve durable facts strictly isolated to the specified scheme.
        Zero cross-scheme fact leakage.
        """
        norm_scheme = (scheme_id or "").strip().lower()
        if not norm_scheme:
            # Hard isolation: no scheme specified -> return empty list
            return []

        query = "SELECT event_id, scheme_id, entity, event_text, timestamp, importance, source, confidence, status FROM scheme_memory_events WHERE scheme_id = ?"
        params: List[Any] = [norm_scheme]

        if entity:
            query += " AND (UPPER(entity) = ? OR UPPER(entity) LIKE ?)"
            clean_e = entity.strip().upper()
            params.extend([clean_e, f"%{clean_e}%"])

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        conn = self._get_connection()
        try:
            with self._lock:
                cur = conn.execute(query, params)
                rows = cur.fetchall()
        finally:
            conn.close()

        results = [
            MemoryFact(
                event_id=r["event_id"],
                scheme_id=r["scheme_id"],
                entity=r["entity"],
                event_text=r["event_text"],
                timestamp=r["timestamp"],
                importance=r["importance"],
                source=r["source"] or "",
                confidence=float(r["confidence"]),
                status=r["status"],
            )
            for r in rows
        ]
        return results

    def count_facts(self, scheme_id: str) -> int:
        """Count total stored facts for a specific scheme."""
        norm_scheme = (scheme_id or "").strip().lower()
        conn = self._get_connection()
        try:
            with self._lock:
                cur = conn.execute("SELECT COUNT(*) FROM scheme_memory_events WHERE scheme_id = ?", (norm_scheme,))
                return cur.fetchone()[0]
        finally:
            conn.close()

    def clear_scheme_memory(self, scheme_id: str) -> None:
        """Clear memory for a single scheme without affecting other schemes."""
        norm_scheme = (scheme_id or "").strip().lower()
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM scheme_memory_events WHERE scheme_id = ?", (norm_scheme,))
            conn.commit()
        scheme_ledger = self.memory_dir / norm_scheme / "events.jsonl"
        if scheme_ledger.exists():
            try:
                scheme_ledger.unlink()
            except Exception:
                pass
