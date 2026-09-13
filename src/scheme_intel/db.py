"""
SQLite database for historical catalyst, setup, and trade tracking.

Stores every pipeline run so we can compute success rates, win/loss ratios,
and catalyst-score correlations over time.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .logger import get_logger
from .exceptions import DatabaseError

logger = get_logger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "scheme_intel.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at    TEXT    NOT NULL,
    summary         TEXT,
    source_errors   TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS catalysts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id),
    title           TEXT    NOT NULL,
    url             TEXT,
    score           INTEGER NOT NULL,
    category        TEXT,
    companies       TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS setups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id),
    catalyst_id     INTEGER REFERENCES catalysts(id),
    company         TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    close           REAL,
    entry           REAL,
    stop            REAL,
    target          REAL,
    rsi14           REAL,
    catalyst_score  INTEGER,
    status          TEXT,
    prior_high20    REAL,
    breakout        INTEGER,
    volume_avg      REAL,
    volume_ratio    REAL,
    macd            REAL,
    macd_signal     REAL,
    macd_hist       REAL,
    week_trend      TEXT,
    dma200          REAL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_id        INTEGER REFERENCES setups(id),
    company         TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    entry_price     REAL,
    stop_price      REAL,
    target_price    REAL,
    entry_date      TEXT,
    exit_date       TEXT,
    exit_price      REAL,
    outcome         TEXT,
    pnl_pct         REAL,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_catalysts_run ON catalysts(run_id);
CREATE INDEX IF NOT EXISTS idx_setups_run    ON setups(run_id);
CREATE INDEX IF NOT EXISTS idx_trades_setup  ON trades(setup_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
"""


class SchemeIntelDB:
    """Thin wrapper around SQLite for scheme-intel historical data."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._create_schema()
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_schema(self) -> None:
        conn = self._conn
        if conn is None:
            return
        try:
            conn.executescript(_SCHEMA)
            logger.info(f"Database schema initialized at {self.db_path}")
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to create schema: {exc}") from exc

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def save_run(
        self,
        generated_at: str,
        catalysts: list[dict],
        setups: list[dict],
        source_errors: list[dict],
        summary: str = "",
    ) -> int:
        """Persist a full pipeline run and return the run ID."""
        conn = self.connect()
        try:
            cursor = conn.execute(
                "INSERT INTO runs (generated_at, summary, source_errors) VALUES (?, ?, ?)",
                (generated_at, summary, json.dumps(source_errors, default=str)),
            )
            run_id = cursor.lastrowid

            catalyst_ids: dict[int, int] = {}
            for cat in catalysts:
                cur = conn.execute(
                    "INSERT INTO catalysts (run_id, title, url, score, category, companies) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        cat.get("title", ""),
                        cat.get("url", ""),
                        cat.get("score", 0),
                        cat.get("category", ""),
                        json.dumps(cat.get("companies", []), default=str),
                    ),
                )
                catalyst_ids[cat.get("score", 0)] = cur.lastrowid

            for setup in setups:
                conn.execute(
                    "INSERT INTO setups (run_id, catalyst_id, company, symbol, close, entry, "
                    "stop, target, rsi14, catalyst_score, status, prior_high20, breakout, "
                    "volume_avg, volume_ratio, macd, macd_signal, macd_hist, week_trend, dma200) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        None,
                        setup.get("company", ""),
                        setup.get("symbol", ""),
                        setup.get("close"),
                        setup.get("entry"),
                        setup.get("stop"),
                        setup.get("target"),
                        setup.get("rsi14"),
                        setup.get("catalyst_score"),
                        setup.get("status"),
                        setup.get("prior_high20"),
                        1 if setup.get("breakout") else 0,
                        setup.get("volume_avg"),
                        setup.get("volume_ratio"),
                        setup.get("macd"),
                        setup.get("macd_signal"),
                        setup.get("macd_hist"),
                        setup.get("week_trend"),
                        setup.get("dma200"),
                    ),
                )

            conn.commit()
            logger.info(
                "Saved run %d: %d catalysts, %d setups",
                run_id,
                len(catalysts),
                len(setups),
            )
            return run_id

        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"Failed to save run: {exc}") from exc

    def record_trade(
        self,
        company: str,
        symbol: str,
        entry_price: float,
        stop_price: float,
        target_price: float,
        entry_date: str,
        setup_id: Optional[int] = None,
        notes: str = "",
    ) -> int:
        """Record a new trade entry and return the trade ID."""
        conn = self.connect()
        try:
            cursor = conn.execute(
                "INSERT INTO trades (setup_id, company, symbol, entry_price, stop_price, "
                "target_price, entry_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (setup_id, company, symbol, entry_price, stop_price, target_price, entry_date, notes),
            )
            conn.commit()
            trade_id = cursor.lastrowid
            logger.info("Recorded trade %d for %s (%s)", trade_id, company, symbol)
            return trade_id
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"Failed to record trade: {exc}") from exc

    def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        exit_date: str,
        outcome: str,
        notes: str = "",
    ) -> None:
        """Close a trade with outcome (WIN / LOSS / BREAKEVEN)."""
        conn = self.connect()
        try:
            row = conn.execute("SELECT entry_price FROM trades WHERE id = ?", (trade_id,)).fetchone()
            if row is None:
                raise DatabaseError(f"Trade {trade_id} not found")
            entry_price = row["entry_price"]
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price else 0.0
            conn.execute(
                "UPDATE trades SET exit_price=?, exit_date=?, outcome=?, pnl_pct=?, notes=? WHERE id=?",
                (exit_price, exit_date, outcome, round(pnl_pct, 2), notes, trade_id),
            )
            conn.commit()
            logger.info("Closed trade %d: %s (%.2f%%)", trade_id, outcome, pnl_pct)
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"Failed to close trade: {exc}") from exc

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_runs(self, limit: int = 50) -> list[dict]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_catalysts_for_run(self, run_id: int) -> list[dict]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM catalysts WHERE run_id = ? ORDER BY score DESC", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_setups_for_run(self, run_id: int) -> list[dict]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM setups WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trades(self, symbol: Optional[str] = None, outcome: Optional[str] = None) -> list[dict]:
        conn = self.connect()
        query = "SELECT * FROM trades WHERE 1=1"
        params: list = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if outcome:
            query += " AND outcome = ?"
            params.append(outcome)
        query += " ORDER BY id DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_all_setups(self) -> list[dict]:
        conn = self.connect()
        rows = conn.execute("SELECT * FROM setups ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def count_runs(self) -> int:
        conn = self.connect()
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    def count_setups(self) -> int:
        conn = self.connect()
        return conn.execute("SELECT COUNT(*) FROM setups").fetchone()[0]

    def count_trades(self) -> int:
        conn = self.connect()
        return conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
