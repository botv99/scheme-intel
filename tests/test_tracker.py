"""
Tests for Stage 2 Automated Outcome Tracking, Telegram Dispatch, and Unified Pipeline Execution.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch
import pytest

try:
    from scheme_intel.stage2.models import (
        Stock, TradeSetup, SetupOutcome, RiskAssessment, TechnicalSnapshot, DailyStockCard
    )
    from scheme_intel.stage2.storage import Stage2Database
    from scheme_intel.stage2.tracker import OutcomeTracker
    from scheme_intel.stage2.pipeline import Stage2Pipeline
    from scheme_intel.stage2.providers.mock import MockProvider
    from scheme_intel.main import run as main_run
except ImportError:
    from src.scheme_intel.stage2.models import (
        Stock, TradeSetup, SetupOutcome, RiskAssessment, TechnicalSnapshot, DailyStockCard
    )
    from src.scheme_intel.stage2.storage import Stage2Database
    from src.scheme_intel.stage2.tracker import OutcomeTracker
    from src.scheme_intel.stage2.pipeline import Stage2Pipeline
    from src.scheme_intel.stage2.providers.mock import MockProvider
    from src.scheme_intel.main import run as main_run


@pytest.fixture
def temp_db(tmp_path: Path) -> Stage2Database:
    db_file = tmp_path / "test_outcomes.db"
    return Stage2Database(db_file)


def _make_sample_setup(symbol: str = "PRAJIND.NS", name: str = "Praj Industries") -> TradeSetup:
    stock = Stock(name=name, symbol=symbol)
    risk = RiskAssessment(
        passed=True,
        entry_min=518.0,
        entry_max=525.0,
        ideal_entry=520.0,
        max_acceptable_entry=526.0,
        min_rr_at_max_entry=1.5,
        trigger_condition="Break ₹525 on volume",
        stop_loss=495.0,
        target_1=565.0,
        target_2=590.0,
        target_3=620.0,
        risk_reward_ratio=1.8,
        rr_basis="Ideal Entry ₹520",
        technical_invalidation="Daily close below stop loss ₹495.00",
        breakout_failure_condition="Rejection below ₹525",
        share_quantity=100,
        capital_deployed=52000.0,
        position_size_pct=5.2,
        maximum_loss_at_stop=2500.0,
        actual_risk_pct=0.25,
    )
    return TradeSetup(
        setup_id=f"SETUP-{symbol.replace('.', '_')}-20260923",
        analysis_date="2026-09-23",
        setup_date="2026-09-24",
        next_trading_session="24 Sep 2026 (Thursday)",
        market_close_timestamp="2026-09-23T15:30:00+05:30",
        stock=stock,
        status="QUALIFIED_SETUP",
        risk=risk,
    )


class TestOutcomeTracker:
    def test_entry_trigger_detection(self, temp_db: Stage2Database):
        setup = _make_sample_setup()
        temp_db.save_setup(setup)

        tracker = OutcomeTracker(temp_db)

        # Snapshot where price trades within entry zone (518 - 525): low=519, high=528
        snap = TechnicalSnapshot(
            close=524.0,
            high=528.0,
            low=519.0,
            volume=400_000,
            support=495.0,
            resistance=525.0,
        )
        result = tracker.evaluate_active_setups({"PRAJIND.NS": snap}, session_date="2026-09-24")

        assert len(result["triggered"]) == 1
        outcome = result["triggered"][0]
        assert outcome.entry_triggered is True
        assert outcome.entry_date == "2026-09-24"
        assert outcome.actual_entry_price == 520.0  # Ideal entry fill
        assert outcome.holding_period_days == 1

        # Verify saved in SQLite
        saved = temp_db.get_outcome(setup.setup_id)
        assert saved is not None
        assert saved.entry_triggered is True

    def test_mfe_mae_and_holding_period_tracking(self, temp_db: Stage2Database):
        setup = _make_sample_setup()
        temp_db.save_setup(setup)

        # Pre-seed entered outcome on day 1
        initial = SetupOutcome(
            setup_id=setup.setup_id,
            symbol="PRAJIND.NS",
            entry_triggered=True,
            actual_entry_price=520.0,
            entry_date="2026-09-24",
            holding_period_days=1,
            mfe_pct=2.0,
            mae_pct=-1.0,
        )
        temp_db.save_outcome(initial)

        tracker = OutcomeTracker(temp_db)

        # Day 2 session: High = 546 (+5%), Low = 514.8 (-1%)
        snap = TechnicalSnapshot(
            close=540.0,
            high=546.0,
            low=514.8,
            volume=350_000,
        )
        result = tracker.evaluate_active_setups({"PRAJIND.NS": snap}, session_date="2026-09-25")

        saved = temp_db.get_outcome(setup.setup_id)
        assert saved is not None
        assert saved.holding_period_days == 2
        assert saved.mfe_pct == 5.0  # (546 - 520)/520 * 100
        assert saved.mae_pct == -1.0
        assert saved.target_hit is False
        assert saved.stop_hit is False

    def test_target_1_hit_detection(self, temp_db: Stage2Database):
        setup = _make_sample_setup()  # Target 1 = 565.0
        temp_db.save_setup(setup)

        # Pre-seed entered position
        initial = SetupOutcome(
            setup_id=setup.setup_id,
            symbol="PRAJIND.NS",
            entry_triggered=True,
            actual_entry_price=520.0,
            entry_date="2026-09-24",
            holding_period_days=2,
        )
        temp_db.save_outcome(initial)

        tracker = OutcomeTracker(temp_db)

        # Day 3 session: High = 568.0 (above Target 1 of 565.0)
        snap = TechnicalSnapshot(
            close=562.0,
            high=568.0,
            low=535.0,
            volume=800_000,
        )
        result = tracker.evaluate_active_setups({"PRAJIND.NS": snap}, session_date="2026-09-26")

        assert len(result["target_hits"]) == 1
        saved = temp_db.get_outcome(setup.setup_id)
        assert saved is not None
        assert saved.target_hit is True
        assert saved.exit_price == 565.0
        assert saved.exit_date == "2026-09-26"
        assert saved.realized_pnl_pct == round(((565.0 - 520.0) / 520.0) * 100, 2)  # +8.65%

    def test_stop_loss_hit_detection(self, temp_db: Stage2Database):
        setup = _make_sample_setup()  # Stop loss = 495.0
        temp_db.save_setup(setup)

        # Pre-seed entered position
        initial = SetupOutcome(
            setup_id=setup.setup_id,
            symbol="PRAJIND.NS",
            entry_triggered=True,
            actual_entry_price=520.0,
            entry_date="2026-09-24",
            holding_period_days=1,
        )
        temp_db.save_outcome(initial)

        tracker = OutcomeTracker(temp_db)

        # Breakdown session: Low = 490.0 (below stop loss 495.0)
        snap = TechnicalSnapshot(
            close=492.0,
            high=522.0,
            low=490.0,
            volume=600_000,
        )
        result = tracker.evaluate_active_setups({"PRAJIND.NS": snap}, session_date="2026-09-25")

        assert len(result["stop_hits"]) == 1
        saved = temp_db.get_outcome(setup.setup_id)
        assert saved is not None
        assert saved.stop_hit is True
        assert saved.exit_price == 495.0
        assert saved.exit_date == "2026-09-25"
        assert saved.realized_pnl_pct == round(((495.0 - 520.0) / 520.0) * 100, 2)  # -4.81%

    def test_closed_trade_not_reprocessed(self, temp_db: Stage2Database):
        setup = _make_sample_setup()
        temp_db.save_setup(setup)

        # Pre-seed closed trade
        initial = SetupOutcome(
            setup_id=setup.setup_id,
            symbol="PRAJIND.NS",
            entry_triggered=True,
            actual_entry_price=520.0,
            target_hit=True,
            exit_price=565.0,
        )
        temp_db.save_outcome(initial)

        tracker = OutcomeTracker(temp_db)
        snap = TechnicalSnapshot(close=570.0, high=575.0, low=560.0, volume=300_000)
        result = tracker.evaluate_active_setups({"PRAJIND.NS": snap}, session_date="2026-09-27")

        assert len(result["target_hits"]) == 0
        assert len(result["active_positions"]) == 0

    def test_position_expiry_at_max_setup_age(self, temp_db: Stage2Database):
        setup = _make_sample_setup()
        temp_db.save_setup(setup)

        tracker = OutcomeTracker(temp_db, max_setup_age_days=5)

        # Day 1: Trigger entry
        snap_day1 = TechnicalSnapshot(close=522.0, high=525.0, low=518.0, volume=300_000)
        tracker.evaluate_active_setups({"PRAJIND.NS": snap_day1}, session_date="2026-09-24")

        outcome = temp_db.get_outcome(setup.setup_id)
        assert outcome.entry_triggered is True
        assert outcome.holding_period_days == 1
        assert outcome.expired is False

        # Days 2 to 4: Inside range (no target, no stop)
        for day, date in enumerate(["2026-09-25", "2026-09-26", "2026-09-27"], start=2):
            snap = TechnicalSnapshot(close=523.0, high=535.0, low=510.0, volume=200_000)
            res = tracker.evaluate_active_setups({"PRAJIND.NS": snap}, session_date=date)
            assert len(res["active_positions"]) == 1
            assert len(res["expired"]) == 0

        outcome = temp_db.get_outcome(setup.setup_id)
        assert outcome.holding_period_days == 4
        assert outcome.expired is False

        # Day 5: Reaches max_setup_age_days (5) -> must EXPIRE
        snap_day5 = TechnicalSnapshot(close=526.0, high=530.0, low=515.0, volume=250_000)
        res_day5 = tracker.evaluate_active_setups({"PRAJIND.NS": snap_day5}, session_date="2026-09-28")

        assert len(res_day5["expired"]) == 1
        assert len(res_day5["active_positions"]) == 0
        assert "EXPIRED POSITIONS (MAX AGE REACHED)" in res_day5["summary_text"]
        assert "PRAJIND.NS" in res_day5["summary_text"]

        outcome_final = temp_db.get_outcome(setup.setup_id)
        assert outcome_final.expired is True
        assert outcome_final.target_hit is False
        assert outcome_final.stop_hit is False
        assert outcome_final.holding_period_days == 5
        assert outcome_final.exit_price == 526.0
        assert outcome_final.exit_date == "2026-09-28"
        assert outcome_final.realized_pnl_pct == round(((526.0 - 520.0) / 520.0) * 100, 2)  # +1.15%

        # Subsequent day: already expired trade must not be reprocessed
        snap_day6 = TechnicalSnapshot(close=530.0, high=540.0, low=520.0, volume=200_000)
        res_day6 = tracker.evaluate_active_setups({"PRAJIND.NS": snap_day6}, session_date="2026-09-29")
        assert len(res_day6["expired"]) == 0
        assert len(res_day6["active_positions"]) == 0


class TestStage2PipelineTelegramDispatch:
    @patch('scheme_intel.stage2.pipeline.send_telegram', return_value=True)
    def test_pipeline_dispatch_sends_sections(self, mock_send, tmp_path: Path):
        db_file = tmp_path / "dispatch_test.db"
        pipeline = Stage2Pipeline(
            provider=MockProvider(),
            db_path=db_file,
            mode="mock",
        )
        result = pipeline.run(dry_run=True, session_date="2026-09-23", send=True)

        assert result is not None
        assert mock_send.call_count >= 3  # Section 1, 2, 3 dispatched


class TestMainUnifiedExecution:
    @patch('scheme_intel.main.Pipeline.run')
    @patch('scheme_intel.stage2.pipeline.Stage2Pipeline.run')
    def test_main_run_unifies_stage1_and_stage2(self, mock_stage2, mock_stage1):
        mock_stage1.return_value = {
            "catalysts": ["Praj GOBARdhan"],
            "setups": ["PRAJIND setup"],
            "source_errors": [],
        }
        mock_stage2.return_value = {
            "session_info": Mock(),
            "cards": [],
            "setups": [],
        }

        report = main_run(send=False, stage=2)
        mock_stage1.assert_called_once()
        mock_stage2.assert_called_once()
        assert "catalysts" in report
        assert "stage2" in report
