"""
Trade tracker CLI for scheme-intel.

Usage:
    PYTHONPATH=src python -m scheme_intel.tracker record --company "TruAlt" --symbol TRUALT.NS ...
    PYTHONPATH=src python -m scheme_intel.tracker close  --trade-id 1 --exit 245.50 --outcome WIN
    PYTHONPATH=src python -m scheme_intel.tracker status
    PYTHONPATH=src python -m scheme_intel.tracker dashboard
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .analytics import Analytics
from .db import SchemeIntelDB
from .logger import get_logger

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cmd_record(args: argparse.Namespace) -> None:
    db = SchemeIntelDB()
    trade_id = db.record_trade(
        company=args.company,
        symbol=args.symbol,
        entry_price=args.entry,
        stop_price=args.stop,
        target_price=args.target,
        entry_date=args.date or _now_iso(),
        setup_id=args.setup_id,
        notes=args.notes or "",
    )
    db.close()
    print(f"Trade recorded: ID={trade_id}")


def cmd_close(args: argparse.Namespace) -> None:
    db = SchemeIntelDB()
    db.close_trade(
        trade_id=args.trade_id,
        exit_price=args.exit,
        exit_date=args.date or _now_iso(),
        outcome=args.outcome.upper(),
        notes=args.notes or "",
    )
    db.close()
    print(f"Trade {args.trade_id} closed: {args.outcome.upper()} @ {args.exit}")


def cmd_status(args: argparse.Namespace) -> None:
    db = SchemeIntelDB()
    trades = db.get_trades()
    db.close()

    if not trades:
        print("No trades recorded yet.")
        return

    print(f"{'ID':>4}  {'Company':<25} {'Symbol':<12} {'Entry':>8} {'Exit':>8} {'P&L%':>7} {'Outcome':<10}")
    print("-" * 85)
    for t in trades:
        exit_p = f"{t['exit_price']:.2f}" if t.get("exit_price") else "—"
        pnl = f"{t['pnl_pct']:+.2f}%" if t.get("pnl_pct") is not None else "—"
        outcome = t.get("outcome") or "OPEN"
        print(
            f"{t['id']:>4}  {t['company']:<25} {t['symbol']:<12} "
            f"{t['entry_price']:>8.2f} {exit_p:>8} {pnl:>7} {outcome:<10}"
        )


def cmd_dashboard(args: argparse.Namespace) -> None:
    analytics = Analytics()
    dash = analytics.dashboard()
    analytics.db.close()
    print(json.dumps(dash, indent=2))


def cmd_open_trades(args: argparse.Namespace) -> None:
    db = SchemeIntelDB()
    trades = db.get_trades()
    db.close()
    open_trades = [t for t in trades if not t.get("outcome")]
    if not open_trades:
        print("No open trades.")
        return
    print(f"{'ID':>4}  {'Company':<25} {'Symbol':<12} {'Entry':>8} {'Stop':>8} {'Target':>8} {'Date':<20}")
    print("-" * 95)
    for t in open_trades:
        print(
            f"{t['id']:>4}  {t['company']:<25} {t['symbol']:<12} "
            f"{t['entry_price']:>8.2f} {t['stop_price']:>8.2f} {t['target_price']:>8.2f} "
            f"{t.get('entry_date', ''):<20}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheme-Intel trade tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="Record a new trade")
    rec.add_argument("--company", required=True)
    rec.add_argument("--symbol", required=True)
    rec.add_argument("--entry", type=float, required=True)
    rec.add_argument("--stop", type=float, required=True)
    rec.add_argument("--target", type=float, required=True)
    rec.add_argument("--date", default=None)
    rec.add_argument("--setup-id", type=int, default=None)
    rec.add_argument("--notes", default=None)

    close_p = sub.add_parser("close", help="Close a trade")
    close_p.add_argument("--trade-id", type=int, required=True)
    close_p.add_argument("--exit", type=float, required=True)
    close_p.add_argument("--outcome", required=True, choices=["WIN", "LOSS", "BREAKEVEN"])
    close_p.add_argument("--date", default=None)
    close_p.add_argument("--notes", default=None)

    sub.add_parser("status", help="Show all trades")
    sub.add_parser("dashboard", help="Full analytics dashboard")
    sub.add_parser("open", help="Show open trades")

    args = parser.parse_args()

    if args.command == "record":
        cmd_record(args)
    elif args.command == "close":
        cmd_close(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)
    elif args.command == "open":
        cmd_open_trades(args)


if __name__ == "__main__":
    main()
