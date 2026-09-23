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
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                      INTEGER NOT NULL REFERENCES runs(id),
    title                       TEXT    NOT NULL,
    url                         TEXT,
    score                       INTEGER NOT NULL,
    category                    TEXT,
    companies                   TEXT,
    catalyst_type               TEXT,
    headline                    TEXT,
    source                      TEXT,
    source_tier                 INTEGER DEFAULT 3,
    published_at                TEXT,
    event_date                  TEXT,
    confidence                  REAL    DEFAULT 0.0,
    sentiment_label             TEXT    DEFAULT 'neutral',
    expected_duration           TEXT    DEFAULT 'medium-term',
    affected_business_segment   TEXT,
    related_scheme              TEXT,
    related_sector              TEXT,
    created_at                  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS setups (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES runs(id),
    catalyst_id         INTEGER REFERENCES catalysts(id),
    company             TEXT    NOT NULL,
    symbol              TEXT    NOT NULL,
    close               REAL,
    entry               REAL,
    stop                REAL,
    target              REAL,
    rsi14               REAL,
    catalyst_score      INTEGER,
    status              TEXT,
    prior_high20        REAL,
    breakout            INTEGER,
    volume_avg          REAL,
    volume_ratio        REAL,
    macd                REAL,
    macd_signal         REAL,
    macd_hist           REAL,
    week_trend          TEXT,
    dma200              REAL,
    sma100              REAL,
    roc10               REAL,
    roc21               REAL,
    prior_high50        REAL,
    breakout_dist_pct   REAL,
    atr_pct             REAL,
    volatility_regime   TEXT,
    support             REAL,
    resistance          REAL,
    swing_high          REAL,
    swing_low           REAL,
    rs_nifty            REAL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
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

CREATE TABLE IF NOT EXISTS historical_prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    volume          REAL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS alert_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key       TEXT    NOT NULL UNIQUE,
    level           TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    chat_id         TEXT,
    sent_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_catalysts_run    ON catalysts(run_id);
CREATE INDEX IF NOT EXISTS idx_setups_run       ON setups(run_id);
CREATE INDEX IF NOT EXISTS idx_trades_setup     ON trades(setup_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol    ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_hist_prices_sym  ON historical_prices(symbol, date);
CREATE INDEX IF NOT EXISTS idx_alert_key        ON alert_history(alert_key);
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
            self._migrate_columns(conn)
            logger.info(f"Database schema initialized at {self.db_path}")
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to create schema: {exc}") from exc

    def _migrate_columns(self, conn: sqlite3.Connection) -> None:
        """Safely ensure new optional columns exist in older database files."""
        catalyst_cols = {
            "catalyst_type": "TEXT",
            "headline": "TEXT",
            "source": "TEXT",
            "source_tier": "INTEGER DEFAULT 3",
            "published_at": "TEXT",
            "event_date": "TEXT",
            "confidence": "REAL DEFAULT 0.0",
            "sentiment_label": "TEXT DEFAULT 'neutral'",
            "expected_duration": "TEXT DEFAULT 'medium-term'",
            "affected_business_segment": "TEXT",
            "related_scheme": "TEXT",
            "related_sector": "TEXT",
        }
        setup_cols = {
            "sma100": "REAL",
            "roc10": "REAL",
            "roc21": "REAL",
            "prior_high50": "REAL",
            "breakout_dist_pct": "REAL",
            "atr_pct": "REAL",
            "volatility_regime": "TEXT",
            "support": "REAL",
            "resistance": "REAL",
            "swing_high": "REAL",
            "swing_low": "REAL",
            "rs_nifty": "REAL",
        }
        # Check existing columns in catalysts
        cursor = conn.execute("PRAGMA table_info(catalysts)")
        existing_cat = {row["name"] for row in cursor.fetchall()}
        for col, col_type in catalyst_cols.items():
            if col not in existing_cat:
                try:
                    conn.execute(f"ALTER TABLE catalysts ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass

        # Check existing columns in setups
        cursor = conn.execute("PRAGMA table_info(setups)")
        existing_setups = {row["name"] for row in cursor.fetchall()}
        for col, col_type in setup_cols.items():
            if col not in existing_setups:
                try:
                    conn.execute(f"ALTER TABLE setups ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass
        conn.commit()

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
                    "INSERT INTO catalysts ("
                    "run_id, title, url, score, category, companies, "
                    "catalyst_type, headline, source, source_tier, published_at, "
                    "event_date, confidence, sentiment_label, expected_duration, "
                    "affected_business_segment, related_scheme, related_sector"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        cat.get("title", ""),
                        cat.get("url", ""),
                        cat.get("score", 0),
                        cat.get("category", ""),
                        json.dumps(cat.get("companies", []), default=str),
                        cat.get("catalyst_type", cat.get("category", "")),
                        cat.get("headline", cat.get("title", "")),
                        cat.get("source", ""),
                        cat.get("source_tier", 3),
                        cat.get("published_at"),
                        cat.get("event_date"),
                        cat.get("confidence", 0.0),
                        cat.get("sentiment_label", "neutral"),
                        cat.get("expected_duration", "medium-term"),
                        cat.get("affected_business_segment", ""),
                        cat.get("related_scheme", ""),
                        cat.get("related_sector", ""),
                    ),
                )
                catalyst_ids[cat.get("score", 0)] = cur.lastrowid

            for setup in setups:
                conn.execute(
                    "INSERT INTO setups ("
                    "run_id, catalyst_id, company, symbol, close, entry, "
                    "stop, target, rsi14, catalyst_score, status, prior_high20, breakout, "
                    "volume_avg, volume_ratio, macd, macd_signal, macd_hist, week_trend, dma200, "
                    "sma100, roc10, roc21, prior_high50, breakout_dist_pct, atr_pct, "
                    "volatility_regime, support, resistance, swing_high, swing_low, rs_nifty"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        setup.get("catalyst_id"),
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
                        setup.get("sma100"),
                        setup.get("roc10"),
                        setup.get("roc21"),
                        setup.get("prior_high50"),
                        setup.get("breakout_dist_pct"),
                        setup.get("atr_pct"),
                        setup.get("volatility_regime"),
                        setup.get("support"),
                        setup.get("resistance"),
                        setup.get("swing_high"),
                        setup.get("swing_low"),
                        setup.get("rs_nifty"),
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
    # Historical Prices (Phase 2)
    # ------------------------------------------------------------------

    def save_historical_prices(self, symbol: str, rows: list[dict]) -> int:
        """
        Store historical OHLCV rows for a given symbol into SQLite.
        Handles duplicates via INSERT OR REPLACE.
        """
        conn = self.connect()
        saved = 0
        try:
            for r in rows:
                date_val = r.get("date") or r.get("Date")
                if not date_val:
                    continue
                d_str = str(date_val)[:10]
                conn.execute(
                    "INSERT INTO historical_prices (symbol, date, open, high, low, close, volume) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(symbol, date) DO UPDATE SET "
                    "open=excluded.open, high=excluded.high, low=excluded.low, "
                    "close=excluded.close, volume=excluded.volume",
                    (
                        symbol,
                        d_str,
                        r.get("open") if r.get("open") is not None else r.get("Open"),
                        r.get("high") if r.get("high") is not None else r.get("High"),
                        r.get("low") if r.get("low") is not None else r.get("Low"),
                        r.get("close") if r.get("close") is not None else r.get("Close"),
                        r.get("volume") if r.get("volume") is not None else r.get("Volume"),
                    ),
                )
                saved += 1
            conn.commit()
            return saved
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"Failed to save historical prices for {symbol}: {exc}") from exc

    def get_historical_prices(self, symbol: str, limit: int = 120) -> list[dict]:
        """Fetch historical prices for a symbol, ordered ascending by date."""
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM (SELECT * FROM historical_prices WHERE symbol = ? ORDER BY date DESC LIMIT ?) "
            "ORDER BY date ASC",
            (symbol, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Alert History / De-duplication (Phase 8)
    # ------------------------------------------------------------------

    def record_alert(self, alert_key: str, level: str, message: str, chat_id: str = "") -> bool:
        """Record an alert as sent. Returns False if already sent (dedup)."""
        conn = self.connect()
        try:
            conn.execute(
                "INSERT INTO alert_history (alert_key, level, message, chat_id, sent_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (alert_key, level, message, chat_id),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Already exists (duplicate suppressed)
            return False
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"Failed to record alert: {exc}") from exc

    def is_alert_sent(self, alert_key: str) -> bool:
        """Check if an alert key has already been sent."""
        conn = self.connect()
        row = conn.execute("SELECT 1 FROM alert_history WHERE alert_key = ?", (alert_key,)).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Reads & Stats
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

    def count_historical_prices(self, symbol: Optional[str] = None) -> int:
        conn = self.connect()
        if symbol:
            return conn.execute("SELECT COUNT(*) FROM historical_prices WHERE symbol = ?", (symbol,)).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM historical_prices").fetchone()[0]

    def count_alerts(self) -> int:
        conn = self.connect()
        return conn.execute("SELECT COUNT(*) FROM alert_history").fetchone()[0]
