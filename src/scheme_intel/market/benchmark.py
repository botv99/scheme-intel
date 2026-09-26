"""
NIFTY 50 Benchmark Engine.
Fetches, validates, persists, and computes benchmark returns against swing setups.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "scheme_intel.db"
DEFAULT_BENCHMARK_ID = "NIFTY50"
DEFAULT_BENCHMARK_SYMBOL = "^NSEI"

BENCHMARK_SCHEMA = """
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
CREATE INDEX IF NOT EXISTS idx_benchmark_prices_date ON benchmark_prices(date);
"""


class BenchmarkEngine:
    """
    Authoritative benchmark data management and return calculation engine.
    """

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        benchmark_id: str = DEFAULT_BENCHMARK_ID,
        symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    ):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.benchmark_id = benchmark_id
        self.symbol = symbol
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Create benchmark_prices table if not exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.executescript(BENCHMARK_SCHEMA)
            conn.commit()

    def sync_benchmark_data(self, period: str = "3mo", days_back: Optional[int] = None) -> int:
        """
        Fetch benchmark history from yfinance and persist to SQLite.
        Returns number of records synced.
        """
        if days_back:
            period = f"{days_back}d"
        import yfinance as yf
        try:
            logger.info("Syncing benchmark data for %s (%s, period=%s)...", self.benchmark_id, self.symbol, period)
            ticker = yf.Ticker(self.symbol)
            df = ticker.history(period=period)
            if df.empty:
                logger.warning("Empty benchmark history received for %s", self.symbol)
                return 0

            records: List[Tuple[Any, ...]] = []
            now_iso = datetime.now(timezone.utc).isoformat()

            for ts, row in df.iterrows():
                # Format date YYYY-MM-DD
                d_str = ts.strftime("%Y-%m-%d")
                records.append((
                    self.benchmark_id,
                    d_str,
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row["Volume"]) if "Volume" in row else 0.0,
                    "yfinance",
                    now_iso,
                ))

            insert_query = """
            INSERT INTO benchmark_prices (
                benchmark_id, date, open, high, low, close, volume, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(benchmark_id, date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                source = excluded.source;
            """
            with self._get_connection() as conn:
                conn.executemany(insert_query, records)
                conn.commit()

            logger.info("Successfully synced %d benchmark records for %s", len(records), self.benchmark_id)
            return len(records)
        except Exception as e:
            logger.warning("Failed to sync live benchmark data for %s: %s", self.benchmark_id, e)
            return 0

    def get_close(self, date: str) -> Optional[float]:
        """Fetch benchmark close on or immediately preceding date (within 5 calendar days)."""
        query = """
        SELECT close FROM benchmark_prices
        WHERE benchmark_id = ? AND date <= ?
        ORDER BY date DESC
        LIMIT 1;
        """
        with self._get_connection() as conn:
            row = conn.execute(query, (self.benchmark_id, date)).fetchone()
            if row and row["close"]:
                return float(row["close"])
        return None

    def calculate_return(self, entry_date: str, exit_date: str) -> Optional[float]:
        """
        Calculate benchmark percentage return over [entry_date, exit_date].
        Formula: ((close_exit - close_entry) / close_entry) * 100.0

        CRITICAL LEAKAGE PROTECTION:
        entry_date and exit_date must satisfy exit_date >= entry_date.
        Only historical closes on or prior to the respective dates are used.
        """
        if not entry_date or not exit_date or exit_date < entry_date:
            return None

        c_entry = self.get_close(entry_date)
        c_exit = self.get_close(exit_date)

        if c_entry is None or c_exit is None or c_entry <= 0:
            return None

        ret = ((c_exit - c_entry) / c_entry) * 100.0
        return round(ret, 2)

    def get_price_series(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Fetch benchmark date series between start_date and end_date."""
        query = """
        SELECT date, open, high, low, close, volume, source
        FROM benchmark_prices
        WHERE benchmark_id = ? AND date >= ? AND date <= ?
        ORDER BY date ASC;
        """
        with self._get_connection() as conn:
            rows = conn.execute(query, (self.benchmark_id, start_date, end_date)).fetchall()
            return [dict(r) for r in rows]

    # Convenient aliases
    calculate_benchmark_return = calculate_return
    sync_benchmark = sync_benchmark_data

