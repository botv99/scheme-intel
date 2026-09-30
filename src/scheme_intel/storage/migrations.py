"""
Database Migrations and Schema Upgrades for Multi-Scheme Architecture.
Tracks applied migrations and ensures schema isolation and backward compatibility across SQLite tables.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timezone
from ..logger import get_logger

logger = get_logger(__name__)


def apply_migrations(conn: sqlite3.Connection) -> List[str]:
    """Apply incremental migrations safely to the SQLite database with tracking."""
    applied: List[str] = []

    # Migration tracker table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        migration_id    TEXT PRIMARY KEY,
        applied_at      TEXT NOT NULL
    );
    """)

    cursor = conn.execute("SELECT migration_id FROM schema_migrations")
    already_applied = {row[0] for row in cursor.fetchall()}

    def record_migration(m_id: str) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT OR REPLACE INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)", (m_id, now_str))
        applied.append(m_id)
        logger.info("Applied migration: %s", m_id)

    # 1. Benchmark prices table
    if "001_benchmark_prices" not in already_applied:
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
        record_migration("001_benchmark_prices")

    # 2. Stage 2 Setups: ai_provider column
    if "002_stage2_ai_provider" not in already_applied:
        try:
            conn.execute("ALTER TABLE stage2_setups ADD COLUMN ai_provider TEXT;")
        except Exception:
            pass
        record_migration("002_stage2_ai_provider")

    # 3. Stage 2 Setups: scheme_id column
    if "003_stage2_scheme_id" not in already_applied:
        try:
            conn.execute("ALTER TABLE stage2_setups ADD COLUMN scheme_id TEXT DEFAULT 'gobardhan';")
        except Exception:
            pass
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stage2_setups_scheme ON stage2_setups(scheme_id);")
        except Exception:
            pass
        record_migration("003_stage2_scheme_id")

    # 4. Stage 2 Outcomes: expired column
    if "004_stage2_outcomes_expired" not in already_applied:
        try:
            conn.execute("ALTER TABLE stage2_outcomes ADD COLUMN expired INTEGER DEFAULT 0;")
        except Exception:
            pass
        record_migration("004_stage2_outcomes_expired")

    # 5. Catalysts table scheme_id
    if "005_catalysts_scheme_id" not in already_applied:
        try:
            conn.execute("ALTER TABLE catalysts ADD COLUMN scheme_id TEXT DEFAULT 'gobardhan';")
        except Exception:
            pass
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_catalysts_scheme ON catalysts(scheme_id);")
        except Exception:
            pass
        record_migration("005_catalysts_scheme_id")

    # 6. Setups table scheme_id
    if "006_setups_scheme_id" not in already_applied:
        try:
            conn.execute("ALTER TABLE setups ADD COLUMN scheme_id TEXT DEFAULT 'gobardhan';")
        except Exception:
            pass
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_setups_scheme ON setups(scheme_id);")
        except Exception:
            pass
        record_migration("006_setups_scheme_id")

    # 7. Runs table scheme_id
    if "007_runs_scheme_id" not in already_applied:
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN scheme_id TEXT DEFAULT 'gobardhan';")
        except Exception:
            pass
        record_migration("007_runs_scheme_id")

    # 8. Telegram user sessions (active scheme per user)
    if "008_telegram_sessions" not in already_applied:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS telegram_sessions (
            user_id         TEXT PRIMARY KEY,
            active_scheme   TEXT NOT NULL DEFAULT 'gobardhan',
            customer_id     TEXT,
            updated_at      TEXT NOT NULL
        );
        """)
        record_migration("008_telegram_sessions")

    # 9. Customer entitlements table for commercial licensing
    if "009_entitlements" not in already_applied:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS entitlements (
            customer_id     TEXT NOT NULL,
            scheme_id       TEXT NOT NULL,
            enabled         INTEGER NOT NULL DEFAULT 1,
            expires_at      TEXT,
            tier            TEXT NOT NULL DEFAULT 'standard',
            features        TEXT,
            PRIMARY KEY(customer_id, scheme_id)
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entitlements_customer ON entitlements(customer_id);")
        record_migration("009_entitlements")

    # 10. Evidence-backed company-to-scheme relationships
    if "010_company_scheme_relationships" not in already_applied:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS company_scheme_relationships (
            company             TEXT NOT NULL,
            symbol              TEXT,
            scheme_id           TEXT NOT NULL,
            relationship_type   TEXT NOT NULL,
            evidence            TEXT,
            source              TEXT,
            source_date         TEXT,
            confidence          REAL DEFAULT 1.0,
            status              TEXT DEFAULT 'CORE',
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(company, scheme_id)
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_scheme ON company_scheme_relationships(scheme_id);")
        record_migration("010_company_scheme_relationships")

    # 11. Scheme-isolated structured memory facts
    if "011_scheme_memory_events" not in already_applied:
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
        record_migration("011_scheme_memory_events")

    conn.commit()
    logger.debug("Applied database schema migrations successfully (%d new).", len(applied))
    return applied
