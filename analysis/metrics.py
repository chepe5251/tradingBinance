"""Pure metric-computation functions for backtest analysis.

All functions are stateless — they take lists of trade dicts and return
plain dicts/lists. No pandas, no Binance, no I/O. Trivially unit-testable
and importable from walk_forward.py, oos_split.py, or any notebook.

A "trade dict" is the format produced by backtest/backtest.py:
  {
    "symbol": str, "interval": str, "side": str,
    "entry_time": str,            # "YYYY-MM-DD HH:MM UTC"
    "exit_time": str,
    "entry_price": float, "exit_price": float,
    "stop_price": float,  "tp_price": float,
    "pnl_usdt": float,
    "result": str,                # "WIN" | "LOSS" | "TIMEOUT"
    "candles_held": int,
    "score": float,
    "ema_spread": float, "rsi_at_signal": float,
    "vol_ratio": float,  "body_ratio": float,
    "distance_to_tp": float, "distance_to_sl": float,
    "rr_planned": float, "market_phase": str,
  }

NOTE: This module does NOT change the live bot or any strategy parameters.
      It is a pure analysis layer.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import Callable

# ── core stats ────────────────────────────────────────────────────────────────

def compute_stats(trades: list[dict]) -> dict:
    """Return comprehensive statistics for a list of trade dicts.

    Covers all the standard metrics plus:
    - median_pnl, expectancy
    - best_trade, worst_trade
    - max_drawdown (USDT), max_dd_pct (%)
    - max_win_streak, max_loss_streak
    - underwater_trades (trades where cumulative PnL is below its peak)
    """
    _zero: dict = {
        "total": 0, "wins": 0, "losses": 0, "timeouts": 0,
        "winrate": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0,
        "median_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
        "rr_real": 0.0, "profit_factor": 0.0,
        "expectancy": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
        "max_drawdown": 0.0, "max_dd_pct": 0.0,
        "max_win_streak": 0, "max_loss_streak": 0,
        "underwater_trades": 0,
    }
    if not trades:
        return _zero

    wins     = [t for t in trades if t["result"] == "WIN"]
    losses   = [t for t in trades if t["result"] == "LOSS"]
    timeouts = [t for t in trades if t["result"] == "TIMEOUT"]
    total    = len(trades)
    pnls     = [float(t["pnl_usdt"]) for t in trades]

    total_pnl  = sum(pnls)
    avg_pnl    = total_pnl / total
    median_pnl = statistics.median(pnls)
    best_trade  = max(pnls)
    worst_trade = min(pnls)

    avg_win  = sum(float(t["pnl_usdt"]) for t in wins)   / len(wins)   if wins   else 0.0
    avg_loss = sum(float(t["pnl_usdt"]) for t in losses) / len(losses) if losses else 0.0
    rr_real  = avg_win / abs(avg_loss) if losses and avg_loss != 0 else 0.0

    gross_profit  = sum(p for p in pnls if p > 0)
    gross_loss    = abs(sum(p for p in pnls if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    winrate_frac = len(wins) / total
    expectancy   = winrate_frac * avg_win + (1.0 - winrate_frac) * avg_loss

    # Drawdown + streaks in a single pass
    cum_pnl    = 0.0
    peak       = 0.0
    max_dd     = 0.0
    dd_peak    = 0.0
    underwater = 0
    streak_w = streak_l = max_ws = max_ls = 0

    for t in trades:
        cum_pnl += float(t["pnl_usdt"])
        peak     = max(peak, cum_pnl)
        dd       = cum_pnl - peak
        if dd < max_dd:
            max_dd  = dd
            dd_peak = peak
        if dd < 0:
            underwater += 1

        r = t["result"]
        if r == "WIN":
            streak_w += 1
            streak_l  = 0
        elif r == "LOSS":
            streak_l += 1
            streak_w  = 0
        max_ws = max(max_ws, streak_w)
        max_ls = max(max_ls, streak_l)

    max_dd_pct = (abs(max_dd) / dd_peak * 100) if dd_peak > 0 else 0.0

    return {
        "total":             total,
        "wins":              len(wins),
        "losses":            len(losses),
        "timeouts":          len(timeouts),
        "winrate":           winrate_frac * 100,
        "total_pnl":         total_pnl,
        "avg_pnl":           avg_pnl,
        "median_pnl":        median_pnl,
        "avg_win":           avg_win,
        "avg_loss":          avg_loss,
        "rr_real":           rr_real,
        "profit_factor":     profit_factor,
        "expectancy":        expectancy,
        "best_trade":        best_trade,
        "worst_trade":       worst_trade,
        "max_drawdown":      max_dd,
        "max_dd_pct":        max_dd_pct,
        "max_win_streak":    max_ws,
        "max_loss_streak":   max_ls,
        "underwater_trades": underwater,
    }


# ── top-winner concentration ──────────────────────────────────────────────────

def top_winner_concentration(
    trades: list[dict],
    ns: list[int] | None = None,
) -> list[dict]:
    """Measure how much PnL comes from the top N winning trades.

    For each N in ns, returns:
      n             : cutoff
      top_pnl       : sum of top-N trade PnLs
      total_pnl     : total PnL across all trades
      pct_of_total  : top_pnl / total_pnl * 100  (can be >100 if rest is negative)
      stats_excl    : compute_stats on trades excluding the top N

    Example interpretation:
      If top-5 trades represent 80% of total PnL, the edge is highly concentrated.
      If stats_excl shows negative expectancy, the strategy relies on outliers.
    """
    if ns is None:
        ns = [1, 5, 10, 20]
    if not trades:
        return []

    total_pnl     = sum(float(t["pnl_usdt"]) for t in trades)
    sorted_trades = sorted(trades, key=lambda t: float(t["pnl_usdt"]), reverse=True)

    rows = []
    for n in ns:
        n_capped = min(n, len(trades))
        top_n    = sorted_trades[:n_capped]
        rest     = sorted_trades[n_capped:]
        top_pnl  = sum(float(t["pnl_usdt"]) for t in top_n)
        pct      = (top_pnl / total_pnl * 100) if total_pnl != 0 else 0.0
        rows.append({
            "n":            n_capped,
            "top_pnl":      top_pnl,
            "total_pnl":    total_pnl,
            "pct_of_total": pct,
            "stats_excl":   compute_stats(rest),
        })
    return rows


# ── segmentation ──────────────────────────────────────────────────────────────

def segment_trades(
    trades: list[dict],
    key_fn: Callable[[dict], str],
) -> dict[str, dict]:
    """Group trades by key_fn and return compute_stats per group."""
    groups: dict[str, list[dict]] = {}
    for t in trades:
        k = key_fn(t)
        groups.setdefault(k, []).append(t)
    return {k: compute_stats(v) for k, v in groups.items()}


# ── temporal windows (walk-forward) ───────────────────────────────────────────

def rolling_windows(
    trades: list[dict],
    window_days: int,
    step_days: int,
) -> list[dict]:
    """Partition trades into rolling time windows and compute stats per window.

    Trades are sorted by entry_time. The window slides forward by step_days
    each iteration. Windows with zero trades are included (metrics show zeros).

    Returns a list of dicts:
      window_start : "YYYY-MM-DD"
      window_end   : "YYYY-MM-DD" (inclusive)
      n_trades     : number of trades in this window
      stats        : compute_stats result for this window
    """
    if not trades:
        return []

    def _parse(s: str) -> datetime | None:
        # Try progressively shorter prefixes of the entry_time string.
        # "2026-01-15 10:00 UTC" → parse first 16 chars as "%Y-%m-%d %H:%M"
        for n, fmt in ((16, "%Y-%m-%d %H:%M"), (10, "%Y-%m-%d")):
            try:
                return datetime.strptime(s[:n], fmt)
            except ValueError:
                continue
        return None

    dated = [(t, _parse(t.get("entry_time", ""))) for t in trades]
    dated = [(t, d) for t, d in dated if d is not None]
    if not dated:
        return []

    dated.sort(key=lambda x: x[1])
    first_date = dated[0][1].replace(hour=0, minute=0, second=0, microsecond=0)
    last_date  = dated[-1][1].replace(hour=23, minute=59, second=59)

    window_td = timedelta(days=window_days)
    step_td   = timedelta(days=step_days)

    results = []
    cursor = first_date
    while cursor < last_date:
        end = cursor + window_td
        window_trades = [t for t, d in dated if cursor <= d < end]
        results.append({
            "window_start": cursor.strftime("%Y-%m-%d"),
            "window_end":   (end - timedelta(days=1)).strftime("%Y-%m-%d"),
            "n_trades":     len(window_trades),
            "stats":        compute_stats(window_trades),
        })
        cursor += step_td

    return results


# ── in-sample / out-of-sample split ───────────────────────────────────────────

def oos_split(
    trades: list[dict],
    split_date: str | None = None,
    split_pct: float | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split trades into in-sample and out-of-sample portions.

    Supply exactly one of:
      split_date : ISO date string "YYYY-MM-DD" — trades before this date are IS
      split_pct  : float 0..1 — first split_pct fraction of trades are IS

    Returns (in_sample_trades, out_of_sample_trades).
    """
    if not trades:
        return [], []

    if split_date is not None:
        cutoff = datetime.strptime(split_date[:10], "%Y-%m-%d")

        def _date(t: dict) -> datetime:
            s = t.get("entry_time", "")
            try:
                return datetime.strptime(s[:10], "%Y-%m-%d")
            except ValueError:
                return cutoff  # ambiguous → assign to IS boundary

        ins = [t for t in trades if _date(t) < cutoff]
        oos = [t for t in trades if _date(t) >= cutoff]
        return ins, oos

    if split_pct is not None:
        idx = max(1, int(len(trades) * split_pct))
        return trades[:idx], trades[idx:]

    raise ValueError("Provide split_date or split_pct")
