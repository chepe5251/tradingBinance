"""Tests for analysis.metrics and analysis.regime — pure functions only."""
from __future__ import annotations

import pytest

from analysis.metrics import (
    compute_stats,
    oos_split,
    rolling_windows,
    segment_trades,
    top_winner_concentration,
)
from analysis.regime import (
    add_regime_labels,
    classify_ema_regime,
    classify_volatility,
    regime_analysis,
)

# ── fixtures / helpers ────────────────────────────────────────────────────────

def _trade(
    pnl: float,
    result: str,
    entry_time: str = "2026-01-15 10:00 UTC",
    market_phase: str = "UPTREND",
    vol_ratio: float = 1.2,
    score: float = 2.0,
) -> dict:
    return {
        "pnl_usdt":      pnl,
        "result":        result,
        "entry_time":    entry_time,
        "symbol":        "BTCUSDT",
        "interval":      "15m",
        "candles_held":  5,
        "score":         score,
        "vol_ratio":     vol_ratio,
        "market_phase":  market_phase,
    }


def _simple_trades() -> list[dict]:
    """5 trades: 3 wins, 1 loss, 1 timeout."""
    return [
        _trade(10.0,  "WIN"),
        _trade(5.0,   "WIN"),
        _trade(-3.0,  "LOSS"),
        _trade(8.0,   "WIN"),
        _trade(-1.0,  "TIMEOUT"),
    ]


# ── compute_stats ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestComputeStats:
    def test_empty_returns_zeros(self) -> None:
        s = compute_stats([])
        assert s["total"] == 0
        assert s["winrate"] == 0.0
        assert s["profit_factor"] == 0.0
        assert s["expectancy"] == 0.0

    def test_basic_counts(self) -> None:
        s = compute_stats(_simple_trades())
        assert s["total"] == 5
        assert s["wins"] == 3
        assert s["losses"] == 1
        assert s["timeouts"] == 1

    def test_winrate(self) -> None:
        s = compute_stats(_simple_trades())
        assert abs(s["winrate"] - 60.0) < 1e-9

    def test_total_pnl(self) -> None:
        s = compute_stats(_simple_trades())
        assert abs(s["total_pnl"] - 19.0) < 1e-9

    def test_best_and_worst_trade(self) -> None:
        s = compute_stats(_simple_trades())
        assert s["best_trade"] == 10.0
        assert s["worst_trade"] == -3.0

    def test_median_pnl(self) -> None:
        s = compute_stats(_simple_trades())
        # sorted pnls: -3, -1, 5, 8, 10  → median = 5
        assert s["median_pnl"] == 5.0

    def test_profit_factor(self) -> None:
        s = compute_stats(_simple_trades())
        # gross profit = 10+5+8+0 = 23 (TIMEOUT pnl=-1 counts as loss side)
        # actually gross profit = sum of positive pnls = 10+5+8 = 23
        # gross loss = abs(-3 + -1) = 4
        assert abs(s["profit_factor"] - 23.0 / 4.0) < 1e-6

    def test_expectancy_sign_positive(self) -> None:
        s = compute_stats(_simple_trades())
        assert s["expectancy"] > 0.0

    def test_all_wins_profit_factor_zero_denominator(self) -> None:
        trades = [_trade(5.0, "WIN"), _trade(3.0, "WIN")]
        s = compute_stats(trades)
        assert s["profit_factor"] == 0.0  # no losses → gross_loss=0 → guarded

    def test_max_win_streak(self) -> None:
        trades = [
            _trade(1.0, "WIN"),
            _trade(1.0, "WIN"),
            _trade(-1.0, "LOSS"),
            _trade(1.0, "WIN"),
        ]
        s = compute_stats(trades)
        assert s["max_win_streak"] == 2
        assert s["max_loss_streak"] == 1

    def test_max_loss_streak(self) -> None:
        trades = [
            _trade(-1.0, "LOSS"),
            _trade(-1.0, "LOSS"),
            _trade(-1.0, "LOSS"),
            _trade(5.0,  "WIN"),
        ]
        s = compute_stats(trades)
        assert s["max_loss_streak"] == 3

    def test_drawdown_calculated(self) -> None:
        # Sequence that produces a real drawdown:
        # +10, -5, -5 → cum_pnl: 10, 5, 0 → max_dd = 0 - 10 = -10
        trades = [
            _trade(10.0, "WIN"),
            _trade(-5.0, "LOSS"),
            _trade(-5.0, "LOSS"),
        ]
        s = compute_stats(trades)
        assert s["max_drawdown"] == pytest.approx(-10.0, abs=1e-9)
        assert s["max_dd_pct"]   == pytest.approx(100.0, abs=1e-6)

    def test_underwater_trades_count(self) -> None:
        trades = [
            _trade(10.0, "WIN"),
            _trade(-3.0, "LOSS"),   # cum=7, peak=10, underwater
            _trade(-2.0, "LOSS"),   # cum=5, peak=10, underwater
            _trade(6.0,  "WIN"),    # cum=11, new peak, NOT underwater
        ]
        s = compute_stats(trades)
        assert s["underwater_trades"] == 2

    def test_single_trade_win(self) -> None:
        s = compute_stats([_trade(7.0, "WIN")])
        assert s["total"] == 1
        assert s["winrate"] == 100.0
        assert s["expectancy"] == pytest.approx(7.0, abs=1e-9)


# ── top_winner_concentration ──────────────────────────────────────────────────

@pytest.mark.unit
class TestTopWinnerConcentration:
    def test_empty_returns_empty(self) -> None:
        assert top_winner_concentration([]) == []

    def test_top1_is_best_trade(self) -> None:
        trades = _simple_trades()
        rows = top_winner_concentration(trades, ns=[1])
        assert len(rows) == 1
        assert rows[0]["top_pnl"] == 10.0   # best trade

    def test_pct_of_total(self) -> None:
        trades = _simple_trades()
        total_pnl = sum(t["pnl_usdt"] for t in trades)
        rows = top_winner_concentration(trades, ns=[1])
        expected_pct = 10.0 / total_pnl * 100
        assert abs(rows[0]["pct_of_total"] - expected_pct) < 1e-6

    def test_stats_excl_excludes_top_n(self) -> None:
        trades = _simple_trades()
        rows = top_winner_concentration(trades, ns=[1])
        # Excluding top trade (10.0 WIN), rest = 5 WIN, -3 LOSS, 8 WIN, -1 TIMEOUT
        excl = rows[0]["stats_excl"]
        assert excl["total"] == 4
        assert abs(excl["total_pnl"] - 9.0) < 1e-9   # 5 - 3 + 8 - 1

    def test_n_capped_at_trade_count(self) -> None:
        trades = _simple_trades()   # 5 trades
        rows = top_winner_concentration(trades, ns=[100])
        assert rows[0]["n"] == 5     # capped

    def test_default_ns(self) -> None:
        rows = top_winner_concentration(_simple_trades())
        assert len(rows) == 4       # defaults: [1, 5, 10, 20]


# ── segment_trades ────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSegmentTrades:
    def test_segments_by_interval(self) -> None:
        trades = [
            {**_trade(5.0, "WIN"),  "interval": "15m"},
            {**_trade(-2.0, "LOSS"), "interval": "1h"},
            {**_trade(3.0, "WIN"),  "interval": "15m"},
        ]
        result = segment_trades(trades, lambda t: t["interval"])
        assert "15m" in result
        assert "1h"  in result
        assert result["15m"]["total"] == 2
        assert result["1h"]["total"]  == 1

    def test_empty_returns_empty(self) -> None:
        assert segment_trades([], lambda t: "x") == {}


# ── rolling_windows ───────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRollingWindows:
    def test_empty_returns_empty(self) -> None:
        assert rolling_windows([], 30, 15) == []

    def test_single_trade_produces_at_least_one_window(self) -> None:
        trades = [_trade(5.0, "WIN", entry_time="2026-01-10 10:00 UTC")]
        windows = rolling_windows(trades, window_days=30, step_days=30)
        assert len(windows) >= 1
        total_in_windows = sum(w["n_trades"] for w in windows)
        assert total_in_windows == 1

    def test_window_stats_match_trades(self) -> None:
        trades = [
            _trade(5.0, "WIN",  entry_time="2026-01-05 10:00 UTC"),
            _trade(-2.0, "LOSS", entry_time="2026-01-10 10:00 UTC"),
        ]
        windows = rolling_windows(trades, window_days=30, step_days=30)
        # Both trades are within first 30-day window
        first_w = windows[0]
        assert first_w["n_trades"] == 2
        assert abs(first_w["stats"]["total_pnl"] - 3.0) < 1e-9

    def test_non_overlapping_trades_in_separate_windows(self) -> None:
        trades = [
            _trade(5.0, "WIN",  entry_time="2026-01-05 10:00 UTC"),
            _trade(3.0, "WIN",  entry_time="2026-03-05 10:00 UTC"),  # ~60d later
        ]
        windows = rolling_windows(trades, window_days=30, step_days=30)
        # First trade in window 1, second trade in a later window
        counts = [w["n_trades"] for w in windows]
        assert max(counts) == 1        # no window has both trades
        assert sum(counts) == 2        # total trades accounted for


# ── oos_split ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestOosSplit:
    def _dated_trades(self) -> list[dict]:
        return [
            _trade(1.0, "WIN",  entry_time="2026-01-10 10:00 UTC"),
            _trade(2.0, "WIN",  entry_time="2026-02-10 10:00 UTC"),
            _trade(3.0, "WIN",  entry_time="2026-03-10 10:00 UTC"),
            _trade(4.0, "WIN",  entry_time="2026-04-10 10:00 UTC"),
        ]

    def test_split_by_date(self) -> None:
        ins, oos = oos_split(self._dated_trades(), split_date="2026-03-01")
        assert len(ins) == 2   # Jan + Feb
        assert len(oos) == 2   # Mar + Apr

    def test_split_by_pct(self) -> None:
        ins, oos = oos_split(self._dated_trades(), split_pct=0.5)
        assert len(ins) == 2
        assert len(oos) == 2

    def test_split_pct_100_all_in_sample(self) -> None:
        ins, oos = oos_split(self._dated_trades(), split_pct=1.0)
        assert len(ins) == 4
        assert len(oos) == 0

    def test_empty_returns_empty_both(self) -> None:
        ins, oos = oos_split([], split_pct=0.7)
        assert ins == []
        assert oos == []

    def test_no_split_arg_raises(self) -> None:
        with pytest.raises(ValueError):
            oos_split(self._dated_trades())


# ── classify_ema_regime ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestClassifyEmaRegime:
    def test_uptrend(self) -> None:
        assert classify_ema_regime(30.0, 25.0, 20.0) == "UPTREND"

    def test_downtrend(self) -> None:
        assert classify_ema_regime(20.0, 25.0, 30.0) == "DOWNTREND"

    def test_mixed_fast_above_trend(self) -> None:
        assert classify_ema_regime(30.0, 20.0, 25.0) == "MIXED"

    def test_all_equal(self) -> None:
        assert classify_ema_regime(25.0, 25.0, 25.0) == "MIXED"


# ── classify_volatility ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestClassifyVolatility:
    def test_high_vol_at_threshold(self) -> None:
        assert classify_volatility(1.5) == "HIGH_VOL"

    def test_high_vol_above(self) -> None:
        assert classify_volatility(2.5) == "HIGH_VOL"

    def test_low_vol_below(self) -> None:
        assert classify_volatility(1.2) == "LOW_VOL"

    def test_custom_threshold(self) -> None:
        assert classify_volatility(2.0, high_threshold=3.0) == "LOW_VOL"
        assert classify_volatility(3.5, high_threshold=3.0) == "HIGH_VOL"


# ── add_regime_labels & regime_analysis ──────────────────────────────────────

@pytest.mark.unit
class TestRegimeAnalysis:
    def test_add_regime_labels_adds_vol_regime(self) -> None:
        trades = [_trade(1.0, "WIN", vol_ratio=2.0), _trade(-1.0, "LOSS", vol_ratio=1.0)]
        add_regime_labels(trades)
        assert trades[0]["vol_regime"] == "HIGH_VOL"
        assert trades[1]["vol_regime"] == "LOW_VOL"

    def test_regime_analysis_keys(self) -> None:
        trades = [
            _trade(5.0,  "WIN",  market_phase="UPTREND",   vol_ratio=2.0),
            _trade(-2.0, "LOSS", market_phase="DOWNTREND", vol_ratio=1.0),
        ]
        result = regime_analysis(trades)
        assert "by_market_phase" in result
        assert "by_vol_regime"   in result
        assert "by_combo"        in result

    def test_regime_analysis_by_phase_counts(self) -> None:
        trades = [
            _trade(5.0,  "WIN",  market_phase="UPTREND"),
            _trade(-2.0, "LOSS", market_phase="UPTREND"),
            _trade(1.0,  "WIN",  market_phase="MIXED"),
        ]
        result = regime_analysis(trades)
        assert result["by_market_phase"]["UPTREND"]["total"] == 2
        assert result["by_market_phase"]["MIXED"]["total"]   == 1


if __name__ == "__main__":
    import unittest
    unittest.main()
