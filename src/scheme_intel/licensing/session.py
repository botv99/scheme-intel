"""
User Session Store for Multi-Scheme Telegram Terminal (Stage 4).
Persists active scheme per user/chat in SQLite to prevent cross-user contamination
and multi-process desynchronization.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timezone

from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "scheme_intel.db"


class SessionStore:
    """Thread-safe and process-safe session manager storing active scheme per user."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._lock = threading.Lock()
        self._in_memory_cache: Dict[str, str] = {}
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS telegram_sessions (
                    user_id         TEXT PRIMARY KEY,
                    active_scheme   TEXT NOT NULL DEFAULT 'gobardhan',
                    customer_id     TEXT,
                    updated_at      TEXT NOT NULL
                );
                """)
                conn.commit()
        except Exception as e:
            logger.debug("SessionStore DB init note: %s", e)

    def get_active_scheme(self, user_id: Optional[str], default_scheme: str = "gobardhan") -> str:
        """Retrieve active scheme for a specific user ID. Never uses global process state."""
        uid = str(user_id or "default_user")

        with self._lock:
            if uid in self._in_memory_cache:
                return self._in_memory_cache[uid]

        try:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT active_scheme FROM telegram_sessions WHERE user_id = ?", (uid,))
                row = cur.fetchone()
                if row and row["active_scheme"]:
                    scheme = row["active_scheme"].lower()
                    with self._lock:
                        self._in_memory_cache[uid] = scheme
                    return scheme
        except Exception as e:
            logger.debug("Failed reading session from DB for %s: %s", uid, e)

        return default_scheme.lower()

    def set_active_scheme(
        self,
        user_id: Optional[str],
        scheme_id: str,
        customer_id: Optional[str] = None,
    ) -> None:
        """Update active scheme for a specific user ID atomically."""
        uid = str(user_id or "default_user")
        norm_scheme = scheme_id.strip().lower()
        now_str = datetime.now(timezone.utc).isoformat()

        with self._lock:
            self._in_memory_cache[uid] = norm_scheme

        try:
            with self._get_connection() as conn:
                conn.execute("""
                INSERT INTO telegram_sessions (user_id, active_scheme, customer_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    active_scheme = excluded.active_scheme,
                    customer_id = coalesce(excluded.customer_id, telegram_sessions.customer_id),
                    updated_at = excluded.updated_at;
                """, (uid, norm_scheme, customer_id, now_str))
                conn.commit()
                logger.info("[SESSION] Switched active scheme for user '%s' to '%s'", uid, norm_scheme)
        except Exception as e:
            logger.warning("Failed writing session to DB for %s: %s", uid, e)

    def clear(self) -> None:
        """Clear memory cache and session table (useful for testing)."""
        with self._lock:
            self._in_memory_cache.clear()
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM telegram_sessions;")
                conn.commit()
        except Exception:
            pass
