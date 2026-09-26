"""
Persistent SQLite Queue for Asynchronous Deep Research Tasks.
Guarantees research jobs survive restarts and process boundaries.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta

from .models import ResearchJob, ResearchStatus
from ..stage2.storage import DEFAULT_STAGE2_DB_PATH
from ..logger import get_logger

logger = get_logger(__name__)

_RESEARCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_jobs (
    job_id          TEXT PRIMARY KEY,
    user_id         TEXT,
    chat_id         TEXT,
    question        TEXT NOT NULL,
    scheme_id       TEXT DEFAULT 'gobardhan',
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    result          TEXT,
    evidence_json   TEXT,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_status ON research_jobs(status);
CREATE INDEX IF NOT EXISTS idx_research_user ON research_jobs(user_id);
"""


class ResearchQueue:
    """Persistent job queue backed by SQLite."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_STAGE2_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _connect(self) -> sqlite3.Connection:
        """Alias for _get_connection."""
        return self._get_connection()


    def _init_schema(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(_RESEARCH_SCHEMA)
            conn.commit()

    def _next_job_id(self) -> str:
        """Generate human-readable ID e.g. R-20260926-001."""
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        query = "SELECT COUNT(*) as cnt FROM research_jobs WHERE job_id LIKE ?;"
        with self._get_connection() as conn:
            row = conn.execute(query, (f"R-{date_str}-%",)).fetchone()
            count = (row["cnt"] if row else 0) + 1
            return f"R-{date_str}-{count:03d}"

    def enqueue_job(
        self,
        question: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        scheme_id: str = "gobardhan",
    ) -> ResearchJob:
        """Enqueue a new research request in persistent storage."""
        job_id = self._next_job_id()
        now_utc = datetime.now(timezone.utc).isoformat()
        job = ResearchJob(
            job_id=job_id,
            user_id=user_id,
            chat_id=chat_id,
            question=question.strip(),
            scheme_id=scheme_id,
            status=ResearchStatus.QUEUED,
            created_at=now_utc,
        )

        query = """
        INSERT INTO research_jobs (job_id, user_id, chat_id, question, scheme_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        with self._get_connection() as conn:
            conn.execute(query, (
                job.job_id,
                job.user_id,
                job.chat_id,
                job.question,
                job.scheme_id,
                job.status.value,
                job.created_at,
            ))
            conn.commit()

        logger.info("Enqueued research job %s: '%s'", job.job_id, job.question[:50])
        return job

    def get_job(self, job_id: str) -> Optional[ResearchJob]:
        """Retrieve a specific job by its ID."""
        query = "SELECT * FROM research_jobs WHERE job_id = ?;"
        with self._get_connection() as conn:
            row = conn.execute(query, (job_id,)).fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def claim_next_job(self) -> Optional[ResearchJob]:
        """Atomically claim the next QUEUED job and set status to RUNNING."""
        now_utc = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute(
                "SELECT job_id FROM research_jobs WHERE status = ? ORDER BY created_at ASC LIMIT 1;",
                (ResearchStatus.QUEUED.value,),
            ).fetchone()
            if not row:
                conn.commit()
                return None

            job_id = row["job_id"]
            cursor = conn.execute(
                "UPDATE research_jobs SET status = ?, started_at = ? WHERE job_id = ? AND status = ?;",
                (ResearchStatus.RUNNING.value, now_utc, job_id, ResearchStatus.QUEUED.value),
            )
            conn.commit()

            if cursor.rowcount == 0:
                # Lost race to another worker
                return None

            return self.get_job(job_id)

    def recover_stale_running_jobs(self, timeout_seconds: float = 300.0) -> int:
        """
        Recover jobs stuck in RUNNING status for longer than timeout_seconds.
        Resets their status to QUEUED so another worker can claim and execute them.
        """
        cutoff_dt = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        cutoff_iso = cutoff_dt.isoformat()
        query = """
        UPDATE research_jobs
        SET status = ?, started_at = NULL
        WHERE status = ? AND (started_at IS NULL OR started_at < ?);
        """
        with self._get_connection() as conn:
            cursor = conn.execute(query, (
                ResearchStatus.QUEUED.value,
                ResearchStatus.RUNNING.value,
                cutoff_iso,
            ))
            conn.commit()
            recovered = cursor.rowcount
            if recovered > 0:
                logger.warning("Recovered %d abandoned RUNNING research jobs back to QUEUED.", recovered)
            return recovered

    def complete_job(
        self,
        job_id: str,
        result: str,
        evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Mark job as COMPLETED and persist results."""
        now_utc = datetime.now(timezone.utc).isoformat()
        ev_json = json.dumps(evidence or [])
        query = """
        UPDATE research_jobs
        SET status = ?, completed_at = ?, result = ?, evidence_json = ?, error = NULL
        WHERE job_id = ?;
        """
        with self._get_connection() as conn:
            conn.execute(query, (ResearchStatus.COMPLETED.value, now_utc, result, ev_json, job_id))
            conn.commit()
        logger.info("Marked research job %s as COMPLETED", job_id)

    def fail_job(self, job_id: str, error: str) -> None:
        """Mark job as FAILED and record error message."""
        now_utc = datetime.now(timezone.utc).isoformat()
        query = "UPDATE research_jobs SET status = ?, completed_at = ?, error = ? WHERE job_id = ?;"
        with self._get_connection() as conn:
            conn.execute(query, (ResearchStatus.FAILED.value, now_utc, str(error)[:500], job_id))
            conn.commit()
        logger.warning("Marked research job %s as FAILED: %s", job_id, error)

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[ResearchJob]:
        """List recent jobs with optional status filter."""
        query = "SELECT * FROM research_jobs"
        params: List[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_job(r) for r in rows]

    def _row_to_job(self, row: sqlite3.Row) -> ResearchJob:
        evidence = json.loads(row["evidence_json"]) if row["evidence_json"] else []
        return ResearchJob(
            job_id=row["job_id"],
            user_id=row["user_id"],
            chat_id=row["chat_id"],
            question=row["question"],
            scheme_id=row["scheme_id"] or "gobardhan",
            status=ResearchStatus(row["status"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            result=row["result"],
            evidence=evidence,
            error=row["error"],
        )

    def get_status_counts(self) -> Dict[str, int]:
        """Return counts of jobs by status."""
        query = "SELECT status, COUNT(*) as cnt FROM research_jobs GROUP BY status;"
        counts = {
            ResearchStatus.QUEUED.value: 0,
            ResearchStatus.RUNNING.value: 0,
            ResearchStatus.COMPLETED.value: 0,
            ResearchStatus.FAILED.value: 0,
        }
        try:
            with self._get_connection() as conn:
                rows = conn.execute(query).fetchall()
                for r in rows:
                    counts[r["status"]] = r["cnt"]
        except Exception as e:
            logger.debug("Failed querying queue status counts: %s", e)
        return counts

