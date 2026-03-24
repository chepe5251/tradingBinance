#!/usr/bin/env python3
"""Walk-forward temporal stability analysis on an existing backtest CSV.

Reads a trade-level CSV produced by backtest/backtest.py, partitions trades
into rolling time windows, and reports metrics per window. This reveals whether
strategy performance is consistent across time or clustered in specific periods.

A strategy with stable edge will show relatively consistent winrate, profit
factor, and expectancy across all windows. Large swings between windows
indicate time-dependent performance that may not generalise.

Usage (from repo root):
    python backtest/walk_forward.py --csv backtest/results/backtest_YYYYMMDD_HHMMSS.csv
    python backtest/walk_forward.py --csv backtest/results/backtest_YYYYMMDD_HHMMSS.csv \\
        --window 30 --step 15 --output my_wf.csv

Options:
    --csv PATH      Path to the backtest trade CSV (required)
    --window DAYS   Window size in days (default: 30)
    --step DAYS     Step between windows in days (default: 15)
    --output PATH   Output CSV path (auto-generated in backtest/results/ if omitted)

Output files:
    walk_forward_YYYYMMDD_HHMMSS.csv  — one row per window with all key metrics

NOTE: This script does NOT change the live bot, strategy parameters, sizing,
      leverage, or any production behaviour. It is a pure analysis tool.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.metrics import compute_stats, rolling_windows  # noqa: E402

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


def _print_wf_table(windows: list[dict]) -> None:
    header = (
        f"  {'Start':<12}  {'End':<12}  {'N':>5}  "
        f"{'WR%':>6}  {'PF':>5}  {'Exp':>8}  {'PnL':>10}  {'MaxDD':>10}"
    )
    print(f"\n{header}")
    print("  " + "-" * 78)
    for w in windows:
        s = w["stats"]
        if s["total"] == 0:
            print(
                f"  {w['window_start']:<12}  {w['window_end']:<12}  "
                f"{'0':>5}  {'—':>6}  {'—':>5}  {'—':>8}  {'—':>10}  {'—':>10}"
            )
            continue
        print(
            f"  {w['window_start']:<12}  {w['window_end']:<12}  "
            f"{s['total']:>5}  "
            f"{s['winrate']:>5.1f}%  "
            f"{s['profit_factor']:>5.2f}  "
            f"{s['expectancy']:>+8.3f}  "
            f"{s['total_pnl']:>+10.2f}  "
            f"{s['max_drawdown']:>+10.2f}"
        )


def _save_wf_csv(windows: list[dict], output_path: str) -> None:
    fieldnames = [
        "window_start", "window_end", "n_trades",
        "wins", "losses", "timeouts",
        "winrate", "profit_factor", "total_pnl",
        "avg_pnl", "median_pnl", "expectancy",
        "avg_win", "avg_loss", "rr_real",
        "max_drawdown", "max_dd_pct",
        "max_win_streak", "max_loss_streak",
        "best_trade", "worst_trade", "underwater_trades",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for w in windows:
            s = w["stats"]
            writer.writerow({
                "window_start":     w["window_start"],
                "window_end":       w["window_end"],
                "n_trades":         w["n_trades"],
                "wins":             s["wins"],
                "losses":           s["losses"],
                "timeouts":         s["timeouts"],
                "winrate":          round(s["winrate"], 2),
                "profit_factor":    round(s["profit_factor"], 3),
                "total_pnl":        round(s["total_pnl"], 4),
                "avg_pnl":          round(s["avg_pnl"], 4),
                "median_pnl":       round(s["median_pnl"], 4),
                "expectancy":       round(s["expectancy"], 4),
                "avg_win":          round(s["avg_win"], 4),
                "avg_loss":         round(s["avg_loss"], 4),
                "rr_real":          round(s["rr_real"], 3),
                "max_drawdown":     round(s["max_drawdown"], 4),
                "max_dd_pct":       round(s["max_dd_pct"], 2),
                "max_win_streak":   s["max_win_streak"],
                "max_loss_streak":  s["max_loss_streak"],
                "best_trade":       round(s["best_trade"], 4),
                "worst_trade":      round(s["worst_trade"], 4),
                "underwater_trades": s["underwater_trades"],
            })


def _print_stability_summary(windows: list[dict]) -> None:
    """Print a brief stability assessment based on window-to-window variance."""
    active = [w for w in windows if w["stats"]["total"] > 0]
    if len(active) < 2:
        return

    pf_vals  = [w["stats"]["profit_factor"] for w in active]
    wr_vals  = [w["stats"]["winrate"]        for w in active]
    exp_vals = [w["stats"]["expectancy"]     for w in active]

    n_positive_pf  = sum(1 for v in pf_vals  if v > 1.0)
    n_positive_exp = sum(1 for v in exp_vals if v > 0.0)

    print(f"\n  Stability summary ({len(active)} active windows):")
    print(f"    WR   range  : {min(wr_vals):.1f}% – {max(wr_vals):.1f}%")
    print(f"    PF   range  : {min(pf_vals):.2f} – {max(pf_vals):.2f}")
    print(f"    Exp  range  : {min(exp_vals):+.3f} – {max(exp_vals):+.3f}")
    print(f"    PF > 1.0    : {n_positive_pf}/{len(active)} windows")
    print(f"    Exp > 0     : {n_positive_exp}/{len(active)} windows")

    consistency = n_positive_pf / len(active)
    if consistency >= 0.75:
        verdict = "CONSISTENT (>=75% of windows profitable)"
    elif consistency >= 0.50:
        verdict = "MODERATE (50-75% of windows profitable)"
    else:
        verdict = "INCONSISTENT (<50% of windows profitable)"
    print(f"    Verdict     : {verdict}")


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Walk-forward temporal stability analysis on backtest CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--csv",    required=True,     help="Path to backtest trade CSV")
    parser.add_argument("--window", type=int, default=30,  help="Window size in days (default: 30)")
    parser.add_argument("--step",   type=int, default=15,  help="Step in days (default: 15)")
    parser.add_argument("--output", default=None,      help="Output CSV path (auto if omitted)")
    args = parser.parse_args()

    print(f"Loading: {args.csv}")
    trades = _load_trades(args.csv)
    if not trades:
        print("No trades found. Exiting.")
        return
    print(f"Loaded {len(trades)} trades")

    overall = compute_stats(trades)
    print(
        f"\nOverall: {overall['total']} trades | "
        f"WR {overall['winrate']:.1f}% | "
        f"PF {overall['profit_factor']:.2f} | "
        f"Exp {overall['expectancy']:+.3f} | "
        f"PnL {_usd(overall['total_pnl'])}"
    )

    windows = rolling_windows(trades, args.window, args.step)
    print(f"\nWalk-forward: {len(windows)} windows  "
          f"(window={args.window}d, step={args.step}d)")
    _print_wf_table(windows)
    _print_stability_summary(windows)

    if args.output:
        out_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
        os.makedirs(results_dir, exist_ok=True)
        out_path = os.path.join(results_dir, f"walk_forward_{ts}.csv")

    _save_wf_csv(windows, out_path)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
