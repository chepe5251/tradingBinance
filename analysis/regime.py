"""Market-regime classification helpers.

Pure, stateless functions that classify market conditions from trade metadata
already present in the backtest CSV. No price data download required.

Regime dimensions:
  1. Trend    : derived from EMA alignment (UPTREND / DOWNTREND / MIXED)
                Already stored as ``market_phase`` in the trade dict.
  2. Volatility: derived from vol_ratio at signal time (HIGH_VOL / LOW_VOL)

These dimensions can be combined (e.g. "UPTREND_HIGH_VOL") to reveal
whether the strategy behaves differently across volatility regimes within
each trend state.

NOTE: This module does NOT change the live bot or any strategy parameters.
      It is a pure analysis layer intended for backtest result inspection.
"""
from __future__ import annotations

# ── classification primitives ─────────────────────────────────────────────────

def classify_ema_regime(ema_fast: float, ema_mid: float, ema_trend: float) -> str:
    """Classify trend regime from three EMA values.

    UPTREND  : ema_fast > ema_mid > ema_trend   (full bull alignment)
    DOWNTREND: ema_fast < ema_mid < ema_trend   (full bear alignment)
    MIXED    : any other configuration
    """
    if ema_fast > ema_mid > ema_trend:
        return "UPTREND"
    if ema_fast < ema_mid < ema_trend:
        return "DOWNTREND"
    return "MIXED"


def classify_volatility(vol_ratio: float, high_threshold: float = 1.5) -> str:
    """Classify volatility regime based on volume ratio at signal.

    HIGH_VOL : vol_ratio >= high_threshold  (above-average volume → more volatility)
    LOW_VOL  : vol_ratio < high_threshold
    """
    return "HIGH_VOL" if vol_ratio >= high_threshold else "LOW_VOL"


def add_regime_labels(trades: list[dict]) -> list[dict]:
    """Add 'vol_regime' to each trade dict in-place using vol_ratio.

    The 'market_phase' field (trend regime) is already present from the backtest.
    This function supplements it with the volatility dimension.

    Returns the same list for chaining.
    """
    for t in trades:
        t["vol_regime"] = classify_volatility(float(t.get("vol_ratio", 0.0)))
    return trades


# ── aggregated regime analysis ────────────────────────────────────────────────

def regime_analysis(trades: list[dict]) -> dict[str, dict]:
    """Break down performance by regime dimensions.

    Returns a dict with three sub-dicts, each mapping a regime label to
    compute_stats output:
      by_market_phase : UPTREND / DOWNTREND / MIXED
      by_vol_regime   : HIGH_VOL / LOW_VOL
      by_combo        : e.g. "UPTREND_HIGH_VOL"

    Adds 'vol_regime' to each trade dict as a side effect.
    """
    from analysis.metrics import segment_trades

    add_regime_labels(trades)

    by_phase = segment_trades(trades, lambda t: str(t.get("market_phase", "MIXED")))
    by_vol   = segment_trades(trades, lambda t: str(t.get("vol_regime",   "UNKNOWN")))
    by_combo = segment_trades(
        trades,
        lambda t: f"{t.get('market_phase', 'MIXED')}_{t.get('vol_regime', 'UNKNOWN')}",
    )

    return {
        "by_market_phase": by_phase,
        "by_vol_regime":   by_vol,
        "by_combo":        by_combo,
    }


def print_regime_report(analysis: dict[str, dict]) -> None:
    """Print a formatted regime breakdown to stdout."""

    def _usd(v: float) -> str:
        return f"{v:+.2f}" if v != 0 else "  0.00"

    def _section(title: str, data: dict[str, dict]) -> None:
        print(f"\n  {title}")
        print(f"  {'Label':<25} {'N':>5}  {'WR%':>6}  {'PF':>5}  {'PnL':>10}  {'Exp':>8}")
        print("  " + "-" * 65)
        for label, s in sorted(data.items()):
            if s["total"] == 0:
                continue
            print(
                f"  {label:<25} {s['total']:>5}  "
                f"{s['winrate']:>5.1f}%  "
                f"{s['profit_factor']:>5.2f}  "
                f"{_usd(s['total_pnl']):>10}  "
                f"{_usd(s['expectancy']):>8}"
            )

    _section("By Market Phase (EMA alignment)",  analysis["by_market_phase"])
    _section("By Volatility Regime (vol_ratio)",  analysis["by_vol_regime"])
    _section("Combined (phase × volatility)",     analysis["by_combo"])
