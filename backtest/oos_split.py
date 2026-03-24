#!/usr/bin/env python3
"""Out-of-sample (OOS) validation on an existing backtest CSV.

Splits a trade-level CSV into an in-sample and an out-of-sample period and
computes metrics for each half. This tests whether the strategy edge holds
on data it was never calibrated against.

If in-sample performance is materially better than OOS, the strategy may be
overfit to the historical period used for parameter selection.

Usage (from repo root):
    # Split by date — trades before 2026-03-01 = IS, from 2026-03-01 = OOS
    python backtest/oos_split.py --csv backtest/results/backtest_YYYYMMDD_HHMMSS.csv \\
        --split 2026-03-01

    # Split by percentage — first 70% = IS, last 30% = OOS
    python backtest/oos_split.py --csv backtest/results/backtest_YYYYMMDD_HHMMSS.csv \\
        --pct 0.7

Options:
    --csv PATH      Path to the backtest trade CSV (required)
    --split DATE    ISO date to split IS/OOS (e.g. 2026-03-01)
    --pct FLOAT     Fraction of trades for in-sample (e.g. 0.7 = 70%)

NOTE: This script does NOT change the live bot, strategy parameters, sizing,
      leverage, or any production behaviour. It is a pure analysis tool.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.metrics import compute_stats, oos_split  # noqa: E402

# ── helpers ────────────────────────────────────────────────────────────────────

def _load_trades(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        trades = []
        for row in reader:
            row["pnl_usdt"]     = float(row.get("pnl_usdt", 0) or 0)
            row["candles_held"] = int(float(row.get("candles_held", 0) or 0))
            row["score"]        = float(row.get("score", 0) or 0)
            trades.append(row)
    return trades


def _usd(v: float) -> str:
    return f"{v:+.2f}"


def _print_stats_block(label: str, s: dict) -> None:
    if s["total"] == 0:
        print(f"\n  [{label}]  — no trades —")
        return
    print(f"\n  [{label}]  {s['total']} trades")
    print(f"    Win / Loss / Timeout : {s['wins']} / {s['losses']} / {s['timeouts']}")
    print(f"    Win rate             : {s['winrate']:.2f}%")
    print(f"    Profit Factor        : {s['profit_factor']:.3f}")
    print(f"    Total PnL            : {_usd(s['total_pnl'])}")
    print(f"    Avg PnL              : {_usd(s['avg_pnl'])}")
    print(f"    Median PnL           : {_usd(s['median_pnl'])}")
    print(f"    Expectancy           : {_usd(s['expectancy'])}")
    print(f"    Avg Win              : {_usd(s['avg_win'])}")
    print(f"    Avg Loss             : {_usd(s['avg_loss'])}")
    print(f"    RR real              : {s['rr_real']:.3f}")
    print(f"    Best trade           : {_usd(s['best_trade'])}")
    print(f"    Worst trade          : {_usd(s['worst_trade'])}")
    print(f"    Max Drawdown         : {_usd(s['max_drawdown'])} ({s['max_dd_pct']:.2f}%)")
    print(f"    Max Win / Loss streak: {s['max_win_streak']} / {s['max_loss_streak']}")


def _print_comparison(s_is: dict, s_oos: dict) -> None:
    def _arrow(v_is: float, v_oos: float, higher_is_better: bool = True) -> str:
        better = v_oos > v_is if higher_is_better else v_oos < v_is
        same   = abs(v_oos - v_is) < 1e-9
        if same:
            return "="
        return "+" if better else "-"

    print("\n  Comparison  (IS → OOS):")
    print(f"    Win rate  : {s_is['winrate']:>6.2f}% → {s_oos['winrate']:>6.2f}%"
          f"  [{_arrow(s_is['winrate'], s_oos['winrate'])}]")
    print(f"    PF        : {s_is['profit_factor']:>6.3f}  → {s_oos['profit_factor']:>6.3f} "
          f" [{_arrow(s_is['profit_factor'], s_oos['profit_factor'])}]")
    print(f"    Expectancy: {s_is['expectancy']:>+7.4f} → {s_oos['expectancy']:>+7.4f}"
          f"  [{_arrow(s_is['expectancy'], s_oos['expectancy'])}]")
    print(f"    RR real   : {s_is['rr_real']:>6.3f}  → {s_oos['rr_real']:>6.3f} "
          f" [{_arrow(s_is['rr_real'], s_oos['rr_real'])}]")

    # Simple verdict
    degrades = sum([
        s_oos["winrate"]        < s_is["winrate"]        * 0.9,
        s_oos["profit_factor"]  < s_is["profit_factor"]  * 0.9,
        s_oos["expectancy"]     < s_is["expectancy"]     * 0.9,
    ])
    if s_oos["total"] == 0:
        verdict = "OOS period has no trades — cannot evaluate."
    elif degrades >= 2:
        verdict = "DEGRADATION detected: OOS materially worse than IS. Possible overfit."
    elif degrades == 1:
        verdict = "MILD degradation on one metric. Monitor carefully."
    else:
        verdict = "STABLE: OOS metrics broadly in line with IS."
    print(f"\n  Verdict: {verdict}")


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="In-sample vs out-of-sample validation on backtest CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--csv", required=True, help="Path to backtest trade CSV")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--split", help="ISO date to split IS/OOS (e.g. 2026-03-01)")
    group.add_argument("--pct",   type=float, help="Fraction for in-sample (0..1), e.g. 0.7")
    args = parser.parse_args()

    trades = _load_trades(args.csv)
    if not trades:
        print("No trades found. Exiting.")
        return
    print(f"Loaded {len(trades)} trades from {args.csv}")

    if args.split:
        ins, oos  = oos_split(trades, split_date=args.split)
        split_lbl = f"date={args.split}"
    else:
        ins, oos  = oos_split(trades, split_pct=args.pct)
        split_lbl = f"pct={args.pct:.0%}"

    print(f"Split: {split_lbl}  →  IS={len(ins)} trades, OOS={len(oos)} trades")
    print("=" * 60)

    s_is  = compute_stats(ins)
    s_oos = compute_stats(oos)

    _print_stats_block("IN-SAMPLE",      s_is)
    _print_stats_block("OUT-OF-SAMPLE",  s_oos)

    if ins and oos:
        _print_comparison(s_is, s_oos)
    print()


if __name__ == "__main__":
    main()
