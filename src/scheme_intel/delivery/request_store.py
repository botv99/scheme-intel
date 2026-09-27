"""
Persistent Request Store for Scheme-Intel Telegram Gateway (Stage 3).
Stores every incoming Telegram message with unique request ID, timestamps,
execution path, status, and responses without creating Git commits.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..logger import get_logger

logger = get_logger(__name__)


class RequestStatus(str, Enum):
    RECEIVED = "RECEIVED"
    ROUTED = "ROUTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExecutionPath(str, Enum):
    FAST = "FAST"
    WORKFLOW = "WORKFLOW"
    RESEARCH = "RESEARCH"


class TelegramRequest(BaseModel):
    """Pydantic model representing a logged Telegram message request."""
    request_id: str
    received_at: str
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    username: Optional[str] = None
    raw_query: str
    normalized_query: str = ""
    resolved_intent: str = "UNKNOWN"
    execution_path: ExecutionPath = ExecutionPath.FAST
    status: RequestStatus = RequestStatus.RECEIVED
    workflow_run_id: Optional[str] = None
    response_sent_at: Optional[str] = None
    error: Optional[str] = None
    response_hash: Optional[str] = None
    update_id: Optional[int] = None


class RequestStore:
    """Thread-safe SQLite storage for Telegram requests and update idempotency."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            default_dir = Path("data")
            default_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(default_dir / "telegram_requests.db")
        else:
            self.db_path = db_path
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telegram_requests (
                    request_id TEXT PRIMARY KEY,
                    received_at TEXT NOT NULL,
                    user_id TEXT,
                    chat_id TEXT,
                    username TEXT,
                    raw_query TEXT NOT NULL,
                    normalized_query TEXT,
                    resolved_intent TEXT,
                    execution_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    workflow_run_id TEXT,
                    response_sent_at TEXT,
                    error TEXT,
                    response_hash TEXT,
                    update_id INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON telegram_requests(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_chat ON telegram_requests(chat_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_update ON telegram_requests(update_id)")
            conn.commit()

    @staticmethod
    def generate_request_id() -> str:
        """Generate unique request identifier such as TG-20260927-123456-ABCD."""
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d-%H%M%S")
        rand_suffix = os.urandom(2).hex().upper()
        return f"TG-{date_str}-{rand_suffix}"

    def is_duplicate_update(self, update_id: int) -> bool:
        """Check whether this update_id has already been processed."""
        if update_id is None:
            return False
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT 1 FROM telegram_requests WHERE update_id = ? LIMIT 1",
                (update_id,),
            )
            return cur.fetchone() is not None

    def log_request(
        self,
        raw_query: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        username: Optional[str] = None,
        update_id: Optional[int] = None,
        normalized_query: str = "",
        resolved_intent: str = "UNKNOWN",
        execution_path: ExecutionPath = ExecutionPath.FAST,
        request_id: Optional[str] = None,
    ) -> TelegramRequest:
        """Log incoming Telegram request BEFORE processing."""
        req_id = request_id or self.generate_request_id()
        now_utc = datetime.now(timezone.utc).isoformat()

        req = TelegramRequest(
            request_id=req_id,
            received_at=now_utc,
            user_id=str(user_id) if user_id is not None else None,
            chat_id=str(chat_id) if chat_id is not None else None,
            username=username,
            raw_query=raw_query,
            normalized_query=normalized_query,
            resolved_intent=resolved_intent,
            execution_path=execution_path,
            status=RequestStatus.RECEIVED,
            update_id=update_id,
        )

        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO telegram_requests (
                    request_id, received_at, user_id, chat_id, username,
                    raw_query, normalized_query, resolved_intent, execution_path,
                    status, workflow_run_id, response_sent_at, error, response_hash, update_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req.request_id,
                    req.received_at,
                    req.user_id,
                    req.chat_id,
                    req.username,
                    req.raw_query,
                    req.normalized_query,
                    req.resolved_intent,
                    req.execution_path.value,
                    req.status.value,
                    req.workflow_run_id,
                    req.response_sent_at,
                    req.error,
                    req.response_hash,
                    req.update_id,
                ),
            )
            conn.commit()

        logger.info(
            "[REQUEST STORE] Logged request %s from chat_id=%s, user_id=%s, path=%s",
            req.request_id,
            req.chat_id,
            req.user_id,
            req.execution_path.value,
        )
        return req

    def get_request(self, request_id: str) -> Optional[TelegramRequest]:
        """Fetch request record by request_id."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM telegram_requests WHERE request_id = ?",
                (request_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return TelegramRequest(
                request_id=row["request_id"],
                received_at=row["received_at"],
                user_id=row["user_id"],
                chat_id=row["chat_id"],
                username=row["username"],
                raw_query=row["raw_query"],
                normalized_query=row["normalized_query"] or "",
                resolved_intent=row["resolved_intent"] or "UNKNOWN",
                execution_path=ExecutionPath(row["execution_path"]),
                status=RequestStatus(row["status"]),
                workflow_run_id=row["workflow_run_id"],
                response_sent_at=row["response_sent_at"],
                error=row["error"],
                response_hash=row["response_hash"],
                update_id=row["update_id"],
            )

    def update_status(
        self,
        request_id: str,
        status: RequestStatus,
        resolved_intent: Optional[str] = None,
        execution_path: Optional[ExecutionPath] = None,
        workflow_run_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update request status and optional workflow run ID / error."""
        with self._lock, self._get_connection() as conn:
            fields = ["status = ?"]
            params: List[Any] = [status.value]

            if resolved_intent is not None:
                fields.append("resolved_intent = ?")
                params.append(resolved_intent)
            if execution_path is not None:
                fields.append("execution_path = ?")
                params.append(execution_path.value)
            if workflow_run_id is not None:
                fields.append("workflow_run_id = ?")
                params.append(workflow_run_id)
            if error is not None:
                fields.append("error = ?")
                params.append(error)

            params.append(request_id)
            cur = conn.execute(
                f"UPDATE telegram_requests SET {', '.join(fields)} WHERE request_id = ?",
                params,
            )
            conn.commit()
            return cur.rowcount > 0

    def mark_completed(
        self,
        request_id: str,
        response_text: str,
        workflow_run_id: Optional[str] = None,
    ) -> bool:
        """Mark request COMPLETED and store response timestamp and hash."""
        now_utc = datetime.now(timezone.utc).isoformat()
        resp_hash = hashlib.sha256(response_text.encode("utf-8")).hexdigest()[:16]

        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE telegram_requests
                SET status = ?, response_sent_at = ?, response_hash = ?, workflow_run_id = COALESCE(?, workflow_run_id)
                WHERE request_id = ?
                """,
                (RequestStatus.COMPLETED.value, now_utc, resp_hash, workflow_run_id, request_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def mark_failed(
        self,
        request_id: str,
        error_msg: str,
        workflow_run_id: Optional[str] = None,
    ) -> bool:
        """Mark request FAILED and record error description."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE telegram_requests
                SET status = ?, error = ?, workflow_run_id = COALESCE(?, workflow_run_id)
                WHERE request_id = ?
                """,
                (RequestStatus.FAILED.value, error_msg[:500], workflow_run_id, request_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def list_requests(self, limit: int = 50) -> List[TelegramRequest]:
        """List most recent requests."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM telegram_requests ORDER BY received_at DESC LIMIT ?",
                (limit,),
            )
            results = []
            for row in cur.fetchall():
                results.append(
                    TelegramRequest(
                        request_id=row["request_id"],
                        received_at=row["received_at"],
                        user_id=row["user_id"],
                        chat_id=row["chat_id"],
                        username=row["username"],
                        raw_query=row["raw_query"],
                        normalized_query=row["normalized_query"] or "",
                        resolved_intent=row["resolved_intent"] or "UNKNOWN",
                        execution_path=ExecutionPath(row["execution_path"]),
                        status=RequestStatus(row["status"]),
                        workflow_run_id=row["workflow_run_id"],
                        response_sent_at=row["response_sent_at"],
                        error=row["error"],
                        response_hash=row["response_hash"],
                        update_id=row["update_id"],
                    )
                )
            return results
