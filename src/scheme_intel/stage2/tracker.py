"""
Automated Trade Outcome Tracking Engine for Stage 2.
Tracks active swing trade setups against subsequent daily market sessions:
- Detects entry trigger occurrence (price in entry zone or above trigger)
- Monitors active positions: holding period, Maximum Favorable Excursion (MFE %), Maximum Adverse Excursion (MAE %)
- Detects Target 1/2/3 hits or Stop Loss hits
- Computes realized PnL % and persists outcomes to SQLite
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from .models import TradeSetup, SetupOutcome, TechnicalSnapshot
from .storage import Stage2Database
from ..logger import get_logger

logger = get_logger(__name__)


class OutcomeTracker:
    """
    Automated tracker that evaluates existing setups against daily market sessions.
    """

    def __init__(
        self,
        db: Stage2Database,
        max_setup_age_days: int = 5,
        config_path: Optional[str] = None,
    ):
        self.db = db
        age = max_setup_age_days
        try:
            from ..config import load_config
            cfg = load_config(config_path)
            age = int(cfg.get("settings", {}).get("max_setup_age_days", max_setup_age_days))
        except Exception:
            pass
        self.max_setup_age_days = age

    def evaluate_active_setups(
        self,
        market_snapshots: Dict[str, TechnicalSnapshot],
        session_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate all historical QUALIFIED_SETUP records against today's market snapshots.

        Args:
            market_snapshots: Dictionary of symbol -> TechnicalSnapshot for today's completed session
            session_date: ISO date string for today's session (defaults to UTC today)

        Returns:
            Dictionary containing updated outcomes, newly triggered entries, closed trades, and summary text.
        """
        today_str = session_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_qualified = self.db.list_setups(status="QUALIFIED_SETUP")

        triggered_entries: List[SetupOutcome] = []
        target_hits: List[SetupOutcome] = []
        stop_hits: List[SetupOutcome] = []
        expired_positions: List[SetupOutcome] = []
        active_positions: List[SetupOutcome] = []

        for setup in all_qualified:
            snap = market_snapshots.get(setup.stock.symbol)
            if not snap or not setup.risk:
                continue

            outcome = self.db.get_outcome(setup.setup_id)
            if not outcome:
                outcome = SetupOutcome(
                    setup_id=setup.setup_id,
                    symbol=setup.stock.symbol,
                    entry_triggered=False,
                    holding_period_days=0,
                )

            # Already closed trade - skip
            if outcome.target_hit or outcome.stop_hit or outcome.expired:
                continue

            risk = setup.risk

            # State 1: Setup waiting for entry trigger
            if not outcome.entry_triggered:
                # Check if today's price action offered a valid entry
                # A setup triggered if price traded within the acceptable entry zone:
                # (today_low <= entry_max and today_high >= entry_min) or (snap.close in zone)
                in_entry_zone = (snap.low <= risk.entry_max and snap.high >= risk.entry_min)
                closing_in_zone = (risk.entry_min <= snap.close <= risk.entry_max)

                if in_entry_zone or closing_in_zone:
                    outcome.entry_triggered = True
                    outcome.entry_date = today_str
                    # Model realistic execution at Ideal Entry (or bounded by entry_max)
                    fill_price = min(risk.entry_max, max(risk.entry_min, risk.ideal_entry))
                    outcome.actual_entry_price = fill_price
                    outcome.holding_period_days = 1
                    triggered_entries.append(outcome)
                    logger.info("Setup %s (%s) TRIGGERED entry at ₹%.2f on %s", setup.setup_id, setup.stock.symbol, fill_price, today_str)

            # State 2: Position is active (either triggered today or previously entered)
            if outcome.entry_triggered and outcome.actual_entry_price:
                entry = outcome.actual_entry_price
                if outcome.entry_date != today_str:
                    outcome.holding_period_days += 1

                # Calculate intra-day and cumulative excursions
                high_excursion = ((snap.high - entry) / entry) * 100.0
                low_excursion = ((snap.low - entry) / entry) * 100.0

                outcome.mfe_pct = round(max(outcome.mfe_pct, high_excursion), 2)
                outcome.mae_pct = round(min(outcome.mae_pct, low_excursion), 2)

                # Check Target 1 Hit
                if snap.high >= risk.target_1:
                    outcome.target_hit = True
                    outcome.exit_price = risk.target_1
                    outcome.exit_date = today_str
                    outcome.realized_pnl_pct = round(((risk.target_1 - entry) / entry) * 100.0, 2)
                    target_hits.append(outcome)
                    logger.info("Setup %s (%s) TARGET 1 HIT at ₹%.2f (+%.2f%%)", setup.setup_id, setup.stock.symbol, risk.target_1, outcome.realized_pnl_pct)

                # Check Stop Loss Hit
                elif snap.low <= risk.stop_loss:
                    outcome.stop_hit = True
                    outcome.exit_price = risk.stop_loss
                    outcome.exit_date = today_str
                    outcome.realized_pnl_pct = round(((risk.stop_loss - entry) / entry) * 100.0, 2)
                    stop_hits.append(outcome)
                    logger.info("Setup %s (%s) STOP LOSS HIT at ₹%.2f (%.2f%%)", setup.setup_id, setup.stock.symbol, risk.stop_loss, outcome.realized_pnl_pct)

                # Check Automatic Expiry (holding_period_days >= max_setup_age_days)
                elif outcome.holding_period_days >= self.max_setup_age_days:
                    outcome.expired = True
                    outcome.exit_price = snap.close
                    outcome.exit_date = today_str
                    outcome.realized_pnl_pct = round(((snap.close - entry) / entry) * 100.0, 2)
                    expired_positions.append(outcome)
                    logger.info("Setup %s (%s) EXPIRED after %d days at ₹%.2f (%.2f%%)", setup.setup_id, setup.stock.symbol, outcome.holding_period_days, snap.close, outcome.realized_pnl_pct)

                else:
                    active_positions.append(outcome)

            # Persist updated outcome to SQLite
            self.db.save_outcome(outcome)

        summary_text = self._format_tracker_summary(
            today_str=today_str,
            triggered=triggered_entries,
            targets=target_hits,
            stops=stop_hits,
            expired=expired_positions,
            active=active_positions,
        )

        return {
            "session_date": today_str,
            "triggered": triggered_entries,
            "target_hits": target_hits,
            "stop_hits": stop_hits,
            "expired": expired_positions,
            "active_positions": active_positions,
            "summary_text": summary_text,
        }

    def _format_tracker_summary(
        self,
        today_str: str,
        triggered: List[SetupOutcome],
        targets: List[SetupOutcome],
        stops: List[SetupOutcome],
        expired: List[SetupOutcome],
        active: List[SetupOutcome],
    ) -> str:
        """Format an informative Telegram update section for active trades."""
        lines = [
            f"📈 *ACTIVE SWING POSITIONS & OUTCOME TRACKER*",
            f"_(Session Date: {today_str})_\n",
        ]

        if not (triggered or targets or stops or expired or active):
            lines.append("• No open or newly triggered swing positions to update.")
            return "\n".join(lines)

        if targets:
            lines.append("🎯 *TARGETS ACHIEVED TODAY:*")
            for o in targets:
                lines.append(f"• *{o.symbol}*: Target 1 hit at ₹{o.exit_price:.2f} (Realized: *+{o.realized_pnl_pct:.2f}%* over {o.holding_period_days} sessions)")
            lines.append("")

        if stops:
            lines.append("🛑 *STOP LOSSES HIT TODAY:*")
            for o in stops:
                lines.append(f"• *{o.symbol}*: Stop hit at ₹{o.exit_price:.2f} (Realized: *{o.realized_pnl_pct:.2f}%* over {o.holding_period_days} sessions)")
            lines.append("")

        if expired:
            lines.append("⌛ *EXPIRED POSITIONS (MAX AGE REACHED):*")
            for o in expired:
                lines.append(f"• *{o.symbol}*: Expired after {o.holding_period_days} sessions | Closed at ₹{o.exit_price:.2f} (Realized: *{o.realized_pnl_pct:+.2f}%*)")
            lines.append("")

        if triggered:
            lines.append("🚀 *NEW POSITIONS TRIGGERED TODAY:*")
            for o in triggered:
                lines.append(f"• *{o.symbol}*: Entry filled at ₹{o.actual_entry_price:.2f}")
            lines.append("")

        if active:
            lines.append("⏳ *ONGOING OPEN POSITIONS:*")
            for o in active:
                lines.append(f"• *{o.symbol}*: Entry ₹{o.actual_entry_price:.2f} | Day {o.holding_period_days} | MFE: +{o.mfe_pct:.1f}% | MAE: {o.mae_pct:.1f}%")
            lines.append("")

        return "\n".join(lines)
