"""
Storage Engine for Stage 2 Setups, Adversarial Debates, and Trade Outcomes.
Stores setups and tracks MFE (Maximum Favorable Excursion) / MAE (Maximum Adverse Excursion).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from .models import TradeSetup, SetupOutcome, Stock
from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_STAGE2_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "scheme_intel.db"

_STAGE2_SCHEMA = """
CREATE TABLE IF NOT EXISTS stage2_setups (
    setup_id                TEXT PRIMARY KEY,
    analysis_date           TEXT NOT NULL,
    setup_date              TEXT NOT NULL,
    next_trading_session    TEXT NOT NULL,
    market_close_timestamp  TEXT,
    symbol                  TEXT NOT NULL,
    company                 TEXT NOT NULL,
    status                  TEXT NOT NULL,
    archetype               TEXT,
    score                   INTEGER,
    candidate_json          TEXT,
    bull_thesis_json        TEXT,
    bear_thesis_json        TEXT,
    debate_json             TEXT,
    risk_json               TEXT,
    wait_json               TEXT,
    no_trade_reason         TEXT,
    telegram_card           TEXT,
    created_at              TEXT NOT NULL,
    ai_provider             TEXT
);

CREATE INDEX IF NOT EXISTS idx_stage2_setups_date ON stage2_setups(analysis_date);
CREATE INDEX IF NOT EXISTS idx_stage2_setups_symbol ON stage2_setups(symbol);
CREATE INDEX IF NOT EXISTS idx_stage2_setups_status ON stage2_setups(status);

CREATE TABLE IF NOT EXISTS stage2_outcomes (
    setup_id            TEXT PRIMARY KEY,
    symbol              TEXT NOT NULL,
    entry_triggered     INTEGER DEFAULT 0,
    actual_entry_price  REAL,
    entry_date          TEXT,
    exit_price          REAL,
    exit_date           TEXT,
    mfe_pct             REAL DEFAULT 0.0,
    mae_pct             REAL DEFAULT 0.0,
    realized_pnl_pct    REAL,
    target_hit          INTEGER DEFAULT 0,
    stop_hit            INTEGER DEFAULT 0,
    expired             INTEGER DEFAULT 0,
    holding_period_days INTEGER DEFAULT 0,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY(setup_id) REFERENCES stage2_setups(setup_id)
);
"""


class Stage2Database:
    """SQLite repository for Stage 2 setups and MFE/MAE tracking."""

    def __init__(self, db_path: Optional[Path | str] = None):
        if db_path is None:
            self.db_path = DEFAULT_STAGE2_DB_PATH
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(_STAGE2_SCHEMA)
            try:
                conn.execute("ALTER TABLE stage2_outcomes ADD COLUMN expired INTEGER DEFAULT 0;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE stage2_setups ADD COLUMN ai_provider TEXT;")
            except Exception:
                pass
            conn.commit()

    def save_setup(self, setup: TradeSetup) -> None:
        """Persist a TradeSetup with debate, risk, and session models."""
        candidate_json = setup.candidate.model_dump_json() if setup.candidate else None
        bull_json = setup.bull_thesis.model_dump_json() if setup.bull_thesis else None
        bear_json = setup.bear_thesis.model_dump_json() if setup.bear_thesis else None
        debate_json = setup.debate.model_dump_json() if setup.debate else None
        risk_json = setup.risk.model_dump_json() if setup.risk else None
        wait_json = setup.wait_conditions.model_dump_json() if setup.wait_conditions else None

        archetype = setup.candidate.archetype if setup.candidate else None
        score = setup.candidate.score if setup.candidate else None

        ai_provider = setup.ai_provider or (setup.debate.provider if setup.debate else None)

        query = """
        INSERT INTO stage2_setups (
            setup_id, analysis_date, setup_date, next_trading_session, market_close_timestamp,
            symbol, company, status, archetype, score, candidate_json, bull_thesis_json,
            bear_thesis_json, debate_json, risk_json, wait_json, no_trade_reason,
            telegram_card, created_at, ai_provider
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(setup_id) DO UPDATE SET
            status = excluded.status,
            archetype = excluded.archetype,
            score = excluded.score,
            candidate_json = excluded.candidate_json,
            bull_thesis_json = excluded.bull_thesis_json,
            bear_thesis_json = excluded.bear_thesis_json,
            debate_json = excluded.debate_json,
            risk_json = excluded.risk_json,
            wait_json = excluded.wait_json,
            no_trade_reason = excluded.no_trade_reason,
            telegram_card = excluded.telegram_card,
            ai_provider = excluded.ai_provider;
        """

        with self._get_connection() as conn:
            conn.execute(query, (
                setup.setup_id,
                setup.analysis_date,
                setup.setup_date,
                setup.next_trading_session,
                setup.market_close_timestamp,
                setup.stock.symbol,
                setup.stock.name,
                setup.status,
                archetype,
                score,
                candidate_json,
                bull_json,
                bear_json,
                debate_json,
                risk_json,
                wait_json,
                setup.no_trade_reason,
                setup.telegram_card,
                setup.created_at,
                ai_provider,
            ))
            conn.commit()
        logger.debug("Saved setup %s (%s - %s)", setup.setup_id, setup.stock.symbol, setup.status)

    def get_setup(self, setup_id: str) -> Optional[TradeSetup]:
        """Retrieve a setup by ID."""
        query = "SELECT * FROM stage2_setups WHERE setup_id = ?;"
        with self._get_connection() as conn:
            row = conn.execute(query, (setup_id,)).fetchone()
            if not row:
                return None
            return self._row_to_setup(row)

    def list_setups(
        self,
        date: Optional[str] = None,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> List[TradeSetup]:
        """List setups with optional filtering."""
        query = "SELECT * FROM stage2_setups WHERE 1=1"
        params: List[Any] = []
        if date:
            query += " AND analysis_date = ?"
            params.append(date)
        if status:
            query += " AND status = ?"
            params.append(status)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        query += " ORDER BY created_at DESC;"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_setup(r) for r in rows]

    def save_outcome(self, outcome: SetupOutcome) -> None:
        """Persist or update trade execution outcome."""
        now = datetime.now(timezone.utc).isoformat()
        query = """
        INSERT INTO stage2_outcomes (
            setup_id, symbol, entry_triggered, actual_entry_price, entry_date,
            exit_price, exit_date, mfe_pct, mae_pct, realized_pnl_pct,
            target_hit, stop_hit, expired, holding_period_days, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(setup_id) DO UPDATE SET
            entry_triggered = excluded.entry_triggered,
            actual_entry_price = excluded.actual_entry_price,
            entry_date = excluded.entry_date,
            exit_price = excluded.exit_price,
            exit_date = excluded.exit_date,
            mfe_pct = excluded.mfe_pct,
            mae_pct = excluded.mae_pct,
            realized_pnl_pct = excluded.realized_pnl_pct,
            target_hit = excluded.target_hit,
            stop_hit = excluded.stop_hit,
            expired = excluded.expired,
            holding_period_days = excluded.holding_period_days,
            updated_at = excluded.updated_at;
        """
        with self._get_connection() as conn:
            conn.execute(query, (
                outcome.setup_id,
                outcome.symbol,
                1 if outcome.entry_triggered else 0,
                outcome.actual_entry_price,
                outcome.entry_date,
                outcome.exit_price,
                outcome.exit_date,
                outcome.mfe_pct,
                outcome.mae_pct,
                outcome.realized_pnl_pct,
                1 if outcome.target_hit else 0,
                1 if outcome.stop_hit else 0,
                1 if outcome.expired else 0,
                outcome.holding_period_days,
                now,
            ))
            conn.commit()

    def get_outcome(self, setup_id: str) -> Optional[SetupOutcome]:
        """Fetch outcome for a setup."""
        query = "SELECT * FROM stage2_outcomes WHERE setup_id = ?;"
        with self._get_connection() as conn:
            row = conn.execute(query, (setup_id,)).fetchone()
            if not row:
                return None
            keys = row.keys()
            return SetupOutcome(
                setup_id=row["setup_id"],
                symbol=row["symbol"],
                entry_triggered=bool(row["entry_triggered"]),
                actual_entry_price=row["actual_entry_price"],
                entry_date=row["entry_date"],
                exit_price=row["exit_price"],
                exit_date=row["exit_date"],
                mfe_pct=row["mfe_pct"],
                mae_pct=row["mae_pct"],
                realized_pnl_pct=row["realized_pnl_pct"],
                target_hit=bool(row["target_hit"]),
                stop_hit=bool(row["stop_hit"]),
                expired=bool(row["expired"]) if "expired" in keys else False,
                holding_period_days=row["holding_period_days"],
            )

    def list_outcomes(self) -> List[SetupOutcome]:
        """Fetch all outcomes ordered by updated_at."""
        query = "SELECT * FROM stage2_outcomes ORDER BY updated_at DESC;"
        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            outcomes = []
            for row in rows:
                keys = row.keys()
                outcomes.append(SetupOutcome(
                    setup_id=row["setup_id"],
                    symbol=row["symbol"],
                    entry_triggered=bool(row["entry_triggered"]),
                    actual_entry_price=row["actual_entry_price"],
                    entry_date=row["entry_date"],
                    exit_price=row["exit_price"],
                    exit_date=row["exit_date"],
                    mfe_pct=row["mfe_pct"] or 0.0,
                    mae_pct=row["mae_pct"] or 0.0,
                    realized_pnl_pct=row["realized_pnl_pct"],
                    target_hit=bool(row["target_hit"]),
                    stop_hit=bool(row["stop_hit"]),
                    expired=bool(row["expired"]) if "expired" in keys else False,
                    holding_period_days=row["holding_period_days"] or 0,
                ))
            return outcomes

    def _row_to_setup(self, row: sqlite3.Row) -> TradeSetup:
        stock = Stock(name=row["company"], symbol=row["symbol"])
        candidate = json.loads(row["candidate_json"]) if row["candidate_json"] else None
        bull = json.loads(row["bull_thesis_json"]) if row["bull_thesis_json"] else None
        bear = json.loads(row["bear_thesis_json"]) if row["bear_thesis_json"] else None
        debate = json.loads(row["debate_json"]) if row["debate_json"] else None
        risk = json.loads(row["risk_json"]) if row["risk_json"] else None
        wait = json.loads(row["wait_json"]) if row["wait_json"] else None

        keys = row.keys()
        ai_provider = row["ai_provider"] if "ai_provider" in keys else None
        if not ai_provider and debate and isinstance(debate, dict):
            ai_provider = debate.get("provider")

        return TradeSetup.model_validate({
            "setup_id": row["setup_id"],
            "analysis_date": row["analysis_date"],
            "setup_date": row["setup_date"],
            "next_trading_session": row["next_trading_session"],
            "market_close_timestamp": row["market_close_timestamp"] or "",
            "stock": stock.model_dump(),
            "status": row["status"],
            "candidate": candidate,
            "bull_thesis": bull,
            "bear_thesis": bear,
            "debate": debate,
            "risk": risk,
            "wait_conditions": wait,
            "no_trade_reason": row["no_trade_reason"],
            "ai_provider": ai_provider,
            "telegram_card": row["telegram_card"] or "",
            "created_at": row["created_at"],
        })
