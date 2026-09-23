"""
Analytics module for scheme-intel performance tracking.

Computes win rate, average ROI, catalyst-score correlations,
drawdowns, technical setup effectiveness, and periodic breakdowns from SQLite.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .db import SchemeIntelDB
from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class TradeSummary:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    win_rate: float = 0.0
    avg_pnl_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "breakevens": self.breakevens,
            "win_rate": round(self.win_rate, 2),
            "avg_pnl_pct": round(self.avg_pnl_pct, 2),
            "avg_win_pct": round(self.avg_win_pct, 2),
            "avg_loss_pct": round(self.avg_loss_pct, 2),
            "best_trade_pct": round(self.best_trade_pct, 2),
            "worst_trade_pct": round(self.worst_trade_pct, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
        }


@dataclass
class SymbolStats:
    symbol: str
    trades: int = 0
    wins: int = 0
    win_rate: float = 0.0
    avg_pnl_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "trades": self.trades,
            "wins": self.wins,
            "win_rate": round(self.win_rate, 2),
            "avg_pnl_pct": round(self.avg_pnl_pct, 2),
        }


@dataclass
class CatalystEffectiveness:
    score_bucket: str
    trades: int = 0
    wins: int = 0
    win_rate: float = 0.0
    avg_pnl_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "score_bucket": self.score_bucket,
            "trades": self.trades,
            "wins": self.wins,
            "win_rate": round(self.win_rate, 2),
            "avg_pnl_pct": round(self.avg_pnl_pct, 2),
        }


class Analytics:
    """Compute performance analytics from the scheme-intel database."""

    def __init__(self, db: Optional[SchemeIntelDB] = None):
        self.db = db or SchemeIntelDB()

    # ------------------------------------------------------------------
    # Trade summary & Drawdown
    # ------------------------------------------------------------------

    def max_drawdown(self) -> float:
        """
        Calculate maximum peak-to-trough drawdown percentage on closed trades.
        """
        trades = self.db.get_trades()
        # sort chronologically by exit_date or id
        closed = sorted(
            [t for t in trades if t.get("outcome")],
            key=lambda x: (x.get("exit_date") or "", x.get("id") or 0),
        )
        if not closed:
            return 0.0

        equity = 100.0
        peak = 100.0
        max_dd = 0.0

        for t in closed:
            pnl = t.get("pnl_pct") or 0.0
            equity *= (1.0 + (pnl / 100.0))
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        return round(max_dd, 2)

    def trade_summary(self) -> TradeSummary:
        """Aggregate win/loss stats and drawdown across all closed trades."""
        trades = self.db.get_trades()
        closed = [t for t in trades if t.get("outcome")]

        if not closed:
            return TradeSummary()

        wins = [t for t in closed if t["outcome"] == "WIN"]
        losses = [t for t in closed if t["outcome"] == "LOSS"]
        breakevens = [t for t in closed if t["outcome"] == "BREAKEVEN"]
        pnls = [t["pnl_pct"] or 0.0 for t in closed]
        win_pnls = [t["pnl_pct"] or 0.0 for t in wins]
        loss_pnls = [t["pnl_pct"] or 0.0 for t in losses]

        return TradeSummary(
            total_trades=len(closed),
            wins=len(wins),
            losses=len(losses),
            breakevens=len(breakevens),
            win_rate=(len(wins) / len(closed) * 100) if closed else 0.0,
            avg_pnl_pct=(sum(pnls) / len(pnls)) if pnls else 0.0,
            avg_win_pct=(sum(win_pnls) / len(win_pnls)) if win_pnls else 0.0,
            avg_loss_pct=(sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0,
            best_trade_pct=max(pnls) if pnls else 0.0,
            worst_trade_pct=min(pnls) if pnls else 0.0,
            total_pnl_pct=round(sum(pnls), 2),
            max_drawdown_pct=self.max_drawdown(),
        )

    # ------------------------------------------------------------------
    # Per-symbol breakdown
    # ------------------------------------------------------------------

    def per_symbol(self) -> list[SymbolStats]:
        """Break down performance by stock symbol."""
        trades = self.db.get_trades()
        closed = [t for t in trades if t.get("outcome")]

        by_symbol: dict[str, list[dict]] = {}
        for t in closed:
            by_symbol.setdefault(t["symbol"], []).append(t)

        results = []
        for symbol, sym_trades in sorted(by_symbol.items()):
            wins = sum(1 for t in sym_trades if t["outcome"] == "WIN")
            pnls = [t["pnl_pct"] or 0.0 for t in sym_trades]
            results.append(SymbolStats(
                symbol=symbol,
                trades=len(sym_trades),
                wins=wins,
                win_rate=(wins / len(sym_trades) * 100) if sym_trades else 0.0,
                avg_pnl_pct=(sum(pnls) / len(pnls)) if pnls else 0.0,
            ))
        return results

    # ------------------------------------------------------------------
    # Catalyst-score correlation
    # ------------------------------------------------------------------

    def catalyst_effectiveness(self) -> list[CatalystEffectiveness]:
        """
        Group closed trades by the catalyst score bucket of their setup
        and compute win rate per bucket.
        """
        trades = self.db.get_trades()
        closed = [t for t in trades if t.get("outcome")]

        if not closed:
            return []

        setups = {s["id"]: s for s in self.db.get_all_setups()}

        buckets: dict[str, list[dict]] = {}
        for t in closed:
            setup = setups.get(t.get("setup_id")) or {}
            score = setup.get("catalyst_score") or t.get("catalyst_score") or 0
            if score >= 90:
                bucket = "90-100"
            elif score >= 75:
                bucket = "75-89"
            elif score >= 60:
                bucket = "60-74"
            else:
                bucket = "Below 60"
            buckets.setdefault(bucket, []).append(t)

        order = ["90-100", "75-89", "60-74", "Below 60"]
        results = []
        for b in order:
            bucket_trades = buckets.get(b, [])
            if not bucket_trades:
                continue
            wins = sum(1 for t in bucket_trades if t["outcome"] == "WIN")
            pnls = [t["pnl_pct"] or 0.0 for t in bucket_trades]
            results.append(CatalystEffectiveness(
                score_bucket=b,
                trades=len(bucket_trades),
                wins=wins,
                win_rate=(wins / len(bucket_trades) * 100) if bucket_trades else 0.0,
                avg_pnl_pct=(sum(pnls) / len(pnls)) if pnls else 0.0,
            ))
        return results

    # ------------------------------------------------------------------
    # Technical-setup effectiveness
    # ------------------------------------------------------------------

    def technical_effectiveness(self) -> dict[str, dict]:
        """
        Evaluate win rate & returns segmented by technical setup criteria:
        Breakout confirmed vs unconfirmed, RSI zones, and MACD confirmation.
        """
        trades = self.db.get_trades()
        closed = [t for t in trades if t.get("outcome")]
        setups = {s["id"]: s for s in self.db.get_all_setups()}

        groups: dict[str, list[dict]] = {
            "breakout_confirmed": [],
            "breakout_unconfirmed": [],
            "rsi_sweet_spot_50_70": [],
            "rsi_outside_sweet_spot": [],
            "macd_hist_positive": [],
            "macd_hist_negative_or_none": [],
        }

        for t in closed:
            setup = setups.get(t.get("setup_id")) or {}
            # Breakout
            if setup.get("breakout"):
                groups["breakout_confirmed"].append(t)
            else:
                groups["breakout_unconfirmed"].append(t)
            # RSI
            rsi = setup.get("rsi14")
            if rsi is not None and 50 <= rsi <= 70:
                groups["rsi_sweet_spot_50_70"].append(t)
            elif rsi is not None:
                groups["rsi_outside_sweet_spot"].append(t)
            # MACD
            hist = setup.get("macd_hist")
            if hist is not None and hist > 0:
                groups["macd_hist_positive"].append(t)
            else:
                groups["macd_hist_negative_or_none"].append(t)

        result = {}
        for name, item_list in groups.items():
            if not item_list:
                result[name] = {"trades": 0, "win_rate": 0.0, "avg_pnl_pct": 0.0}
                continue
            wins = sum(1 for t in item_list if t["outcome"] == "WIN")
            pnls = [t["pnl_pct"] or 0.0 for t in item_list]
            result[name] = {
                "trades": len(item_list),
                "win_rate": round((wins / len(item_list)) * 100, 2),
                "avg_pnl_pct": round(sum(pnls) / len(pnls), 2),
            }
        return result

    # ------------------------------------------------------------------
    # Daily / Weekly / Monthly periodic summary
    # ------------------------------------------------------------------

    def periodic_summary(self, period: str = "monthly") -> list[dict]:
        """
        Group closed trades by daily, weekly, or monthly intervals.
        """
        trades = self.db.get_trades()
        closed = [t for t in trades if t.get("outcome")]
        if not closed:
            return []

        buckets: dict[str, list[dict]] = {}
        for t in closed:
            date_str = t.get("exit_date") or t.get("entry_date") or (t.get("created_at") or "")[:10]
            if not date_str or len(date_str) < 10:
                continue
            try:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            except ValueError:
                continue

            if period == "daily":
                key = dt.strftime("%Y-%m-%d")
            elif period == "weekly":
                key = dt.strftime("%Y-W%W")
            else:  # monthly
                key = dt.strftime("%Y-%m")
            buckets.setdefault(key, []).append(t)

        results = []
        for key in sorted(buckets.keys()):
            items = buckets[key]
            wins = sum(1 for t in items if t["outcome"] == "WIN")
            losses = sum(1 for t in items if t["outcome"] == "LOSS")
            pnls = [t["pnl_pct"] or 0.0 for t in items]
            results.append({
                "period": key,
                "trades": len(items),
                "wins": wins,
                "losses": losses,
                "win_rate": round((wins / len(items)) * 100, 2) if items else 0.0,
                "total_pnl_pct": round(sum(pnls), 2),
                "avg_pnl_pct": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
            })
        return results

    # ------------------------------------------------------------------
    # Pipeline health & full dashboard
    # ------------------------------------------------------------------

    def pipeline_stats(self) -> dict:
        """High-level pipeline health metrics."""
        return {
            "total_runs": self.db.count_runs(),
            "total_setups": self.db.count_setups(),
            "total_trades": self.db.count_trades(),
            "historical_prices": self.db.count_historical_prices(),
            "alerts_sent": self.db.count_alerts(),
            "trade_summary": self.trade_summary().to_dict(),
        }

    def dashboard(self) -> dict:
        """Return the full analytics dashboard as a dict."""
        return {
            "pipeline": self.pipeline_stats(),
            "trade_summary": self.trade_summary().to_dict(),
            "per_symbol": [s.to_dict() for s in self.per_symbol()],
            "catalyst_effectiveness": [c.to_dict() for c in self.catalyst_effectiveness()],
            "technical_effectiveness": self.technical_effectiveness(),
            "monthly_summary": self.periodic_summary("monthly"),
        }
