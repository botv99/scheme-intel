"""Tests for the SQLite database module."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.scheme_intel.db import SchemeIntelDB


@pytest.fixture
def db(tmp_path: Path):
    """Provide a fresh in-memory-like DB for each test."""
    path = tmp_path / "test.db"
    scheme_db = SchemeIntelDB(db_path=path)
    yield scheme_db
    scheme_db.close()


class TestSchemaAndConnection:
    def test_creates_db_file(self, tmp_path: Path):
        path = tmp_path / "new.db"
        scheme_db = SchemeIntelDB(db_path=path)
        scheme_db.connect()
        assert path.exists()
        scheme_db.close()

    def test_connect_idempotent(self, db: SchemeIntelDB):
        conn1 = db.connect()
        conn2 = db.connect()
        assert conn1 is conn2

    def test_count_runs_zero(self, db: SchemeIntelDB):
        assert db.count_runs() == 0

    def test_count_setups_zero(self, db: SchemeIntelDB):
        assert db.count_setups() == 0

    def test_count_trades_zero(self, db: SchemeIntelDB):
        assert db.count_trades() == 0


class TestSaveRun:
    def test_save_empty_run(self, db: SchemeIntelDB):
        run_id = db.save_run(
            generated_at="2026-09-13T10:00:00+00:00",
            catalysts=[],
            setups=[],
            source_errors=[],
            summary="No activity.",
        )
        assert run_id == 1
        assert db.count_runs() == 1

    def test_save_run_with_catalysts(self, db: SchemeIntelDB):
        catalysts = [
            {"title": "Cabinet approval for CBG", "url": "https://example.com", "score": 95, "category": "policy", "companies": ["TruAlt"]},
            {"title": "New tender awarded", "url": "https://example.com/2", "score": 72, "category": "tender", "companies": ["Praj"]},
        ]
        run_id = db.save_run(
            generated_at="2026-09-13T10:00:00+00:00",
            catalysts=catalysts,
            setups=[],
            source_errors=[],
            summary="2 material catalysts.",
        )
        assert run_id == 1
        stored = db.get_catalysts_for_run(run_id)
        assert len(stored) == 2
        assert stored[0]["score"] >= stored[1]["score"]

    def test_save_run_with_setups(self, db: SchemeIntelDB):
        setups = [
            {
                "company": "TruAlt",
                "symbol": "TRUALT.NS",
                "close": 220.0,
                "entry": 225.0,
                "stop": 205.0,
                "target": 260.0,
                "rsi14": 58.5,
                "catalyst_score": 90,
                "status": "qualified",
                "prior_high20": 218.0,
                "breakout": True,
                "volume_avg": 100000,
                "volume_ratio": 1.8,
                "macd": 2.5,
                "macd_signal": 1.2,
                "macd_hist": 1.3,
                "week_trend": "UP",
                "dma200": 195.0,
            }
        ]
        run_id = db.save_run(
            generated_at="2026-09-13T10:00:00+00:00",
            catalysts=[],
            setups=setups,
            source_errors=[],
            summary="1 setup.",
        )
        assert db.count_setups() == 1
        stored = db.get_setups_for_run(run_id)
        assert stored[0]["company"] == "TruAlt"
        assert stored[0]["breakout"] == 1

    def test_save_multiple_runs(self, db: SchemeIntelDB):
        db.save_run("2026-09-12T10:00:00+00:00", [], [], [], "Run 1")
        db.save_run("2026-09-13T10:00:00+00:00", [], [], [], "Run 2")
        assert db.count_runs() == 2

    def test_get_runs_order_descending(self, db: SchemeIntelDB):
        db.save_run("2026-09-12T10:00:00+00:00", [], [], [], "First")
        db.save_run("2026-09-13T10:00:00+00:00", [], [], [], "Second")
        runs = db.get_runs()
        assert runs[0]["summary"] == "Second"
        assert runs[1]["summary"] == "First"


class TestTrades:
    def test_record_trade(self, db: SchemeIntelDB):
        trade_id = db.record_trade(
            company="TruAlt",
            symbol="TRUALT.NS",
            entry_price=220.0,
            stop_price=200.0,
            target_price=260.0,
            entry_date="2026-09-13",
        )
        assert trade_id == 1
        trades = db.get_trades()
        assert len(trades) == 1
        assert trades[0]["outcome"] is None

    def test_close_trade_win(self, db: SchemeIntelDB):
        trade_id = db.record_trade(
            company="TruAlt",
            symbol="TRUALT.NS",
            entry_price=200.0,
            stop_price=180.0,
            target_price=240.0,
            entry_date="2026-09-01",
        )
        db.close_trade(trade_id, exit_price=230.0, exit_date="2026-09-10", outcome="WIN")
        trades = db.get_trades()
        assert trades[0]["outcome"] == "WIN"
        assert trades[0]["pnl_pct"] == 15.0

    def test_close_trade_loss(self, db: SchemeIntelDB):
        trade_id = db.record_trade(
            company="Praj",
            symbol="PRAJIND.NS",
            entry_price=500.0,
            stop_price=470.0,
            target_price=560.0,
            entry_date="2026-09-01",
        )
        db.close_trade(trade_id, exit_price=475.0, exit_date="2026-09-05", outcome="LOSS")
        trades = db.get_trades()
        assert trades[0]["outcome"] == "LOSS"
        assert trades[0]["pnl_pct"] == -5.0

    def test_close_trade_breakeven(self, db: SchemeIntelDB):
        trade_id = db.record_trade(
            company="GAIL",
            symbol="GAIL.NS",
            entry_price=180.0,
            stop_price=170.0,
            target_price=200.0,
            entry_date="2026-09-01",
        )
        db.close_trade(trade_id, exit_price=180.0, exit_date="2026-09-03", outcome="BREAKEVEN")
        trades = db.get_trades()
        assert trades[0]["outcome"] == "BREAKEVEN"
        assert trades[0]["pnl_pct"] == 0.0

    def test_close_nonexistent_trade_raises(self, db: SchemeIntelDB):
        from src.scheme_intel.exceptions import DatabaseError
        with pytest.raises(DatabaseError, match="not found"):
            db.close_trade(999, exit_price=100, exit_date="2026-09-10", outcome="WIN")

    def test_get_trades_filter_by_symbol(self, db: SchemeIntelDB):
        db.record_trade("TruAlt", "TRUALT.NS", 200, 180, 240, "2026-09-01")
        db.record_trade("Praj", "PRAJIND.NS", 500, 470, 560, "2026-09-01")
        trualt = db.get_trades(symbol="TRUALT.NS")
        assert len(trualt) == 1
        assert trualt[0]["symbol"] == "TRUALT.NS"

    def test_get_trades_filter_by_outcome(self, db: SchemeIntelDB):
        t1 = db.record_trade("TruAlt", "TRUALT.NS", 200, 180, 240, "2026-09-01")
        t2 = db.record_trade("Praj", "PRAJIND.NS", 500, 470, 560, "2026-09-01")
        db.close_trade(t1, 230, "2026-09-10", "WIN")
        db.close_trade(t2, 475, "2026-09-05", "LOSS")
        wins = db.get_trades(outcome="WIN")
        assert len(wins) == 1
        losses = db.get_trades(outcome="LOSS")
        assert len(losses) == 1


class TestGetAllSetups:
    def test_empty(self, db: SchemeIntelDB):
        assert db.get_all_setups() == []

    def test_returns_setups(self, db: SchemeIntelDB):
        db.save_run(
            "2026-09-13T10:00:00+00:00",
            catalysts=[],
            setups=[
                {"company": "A", "symbol": "A.NS", "close": 100, "entry": 105,
                 "stop": 95, "target": 120, "rsi14": 55, "catalyst_score": 80,
                 "status": "qualified", "breakout": True, "week_trend": "UP"},
            ],
            source_errors=[],
        )
        all_setups = db.get_all_setups()
        assert len(all_setups) == 1
