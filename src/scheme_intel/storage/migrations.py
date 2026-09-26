"""
Database Migrations and Schema Upgrades.
Ensures backward compatibility across SQLite tables.
"""
from __future__ import annotations

import sqlite3
from typing import Optional
from pathlib import Path
from ..logger import get_logger

logger = get_logger(__name__)


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply incremental migrations safely to the SQLite database."""
    # 1. Benchmark prices table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS benchmark_prices (
        benchmark_id    TEXT NOT NULL,
        date            TEXT NOT NULL,
        open            REAL,
        high            REAL,
        low             REAL,
        close           REAL,
        volume          REAL,
        source          TEXT DEFAULT 'yfinance',
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY(benchmark_id, date)
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_prices_date ON benchmark_prices(date);")

    # 2. Stage 2 Setups: ai_provider column
    try:
        conn.execute("ALTER TABLE stage2_setups ADD COLUMN ai_provider TEXT;")
    except Exception:
        pass

    # 3. Stage 2 Setups: scheme_id column (defaults to gobardhan)
    try:
        conn.execute("ALTER TABLE stage2_setups ADD COLUMN scheme_id TEXT DEFAULT 'gobardhan';")
    except Exception:
        pass

    # 4. Stage 2 Outcomes: expired column
    try:
        conn.execute("ALTER TABLE stage2_outcomes ADD COLUMN expired INTEGER DEFAULT 0;")
    except Exception:
        pass

    conn.commit()
    logger.debug("Applied database schema migrations successfully.")
