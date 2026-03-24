"""Tests for PositionSizer sizing modes."""
from __future__ import annotations

import unittest

import pytest

from sizing import (
    SIZING_MODE_FIXED_MARGIN,
    SIZING_MODE_PCT_BALANCE,
    SIZING_MODE_RISK_BASED,
    PositionSizer,
    SizingInputs,
    is_entry_size_valid,
    normalize_sizing_mode,
)


def _make_inputs(**overrides) -> SizingInputs:
    defaults = dict(
        available_balance=200.0,
        entry_price=100.0,
        stop_price=95.0,
        leverage=20,
        fixed_margin_per_trade_usdt=5.0,
        margin_utilization=0.95,
        risk_per_trade_pct=0.05,
    )
    defaults.update(overrides)
    return SizingInputs(**defaults)


@pytest.mark.unit
class PctBalanceSizingTests(unittest.TestCase):
    def test_5pct_of_200_gives_10(self) -> None:
        sizer = PositionSizer(SIZING_MODE_PCT_BALANCE)
        margin = sizer.margin_to_use(_make_inputs(available_balance=200.0, risk_per_trade_pct=0.05))
        self.assertAlmostEqual(margin, 10.0, places=6)

    def test_5pct_of_100_gives_5(self) -> None:
        sizer = PositionSizer(SIZING_MODE_PCT_BALANCE)
        margin = sizer.margin_to_use(_make_inputs(available_balance=100.0, risk_per_trade_pct=0.05))
        self.assertAlmostEqual(margin, 5.0, places=6)

    def test_zero_balance_returns_zero(self) -> None:
        sizer = PositionSizer(SIZING_MODE_PCT_BALANCE)
        margin = sizer.margin_to_use(_make_inputs(available_balance=0.0))
        self.assertEqual(margin, 0.0)

    def test_margin_capped_at_balance(self) -> None:
        sizer = PositionSizer(SIZING_MODE_PCT_BALANCE)
        margin = sizer.margin_to_use(_make_inputs(available_balance=10.0, risk_per_trade_pct=2.0))
        self.assertLessEqual(margin, 10.0)

    def test_normalize_unknown_mode_falls_back_to_pct_balance(self) -> None:
        self.assertEqual(normalize_sizing_mode("unknown_xyz"), SIZING_MODE_PCT_BALANCE)

    def test_normalize_pct_balance(self) -> None:
        self.assertEqual(normalize_sizing_mode("pct_balance"), SIZING_MODE_PCT_BALANCE)


@pytest.mark.unit
class FixedMarginSizingTests(unittest.TestCase):
    def test_fixed_margin_basic(self) -> None:
        sizer = PositionSizer(SIZING_MODE_FIXED_MARGIN)
        margin = sizer.margin_to_use(_make_inputs(available_balance=100.0, fixed_margin_per_trade_usdt=5.0))
        self.assertAlmostEqual(margin, 5.0, places=6)

    def test_fixed_margin_capped_at_balance(self) -> None:
        sizer = PositionSizer(SIZING_MODE_FIXED_MARGIN)
        margin = sizer.margin_to_use(_make_inputs(available_balance=3.0, fixed_margin_per_trade_usdt=5.0))
        self.assertAlmostEqual(margin, 3.0, places=6)

    def test_fixed_margin_zero_balance_returns_zero(self) -> None:
        sizer = PositionSizer(SIZING_MODE_FIXED_MARGIN)
        margin = sizer.margin_to_use(_make_inputs(available_balance=0.0))
        self.assertEqual(margin, 0.0)

    def test_fixed_margin_zero_fixed_amount_returns_zero(self) -> None:
        sizer = PositionSizer(SIZING_MODE_FIXED_MARGIN)
        margin = sizer.margin_to_use(_make_inputs(fixed_margin_per_trade_usdt=0.0))
        self.assertEqual(margin, 0.0)


@pytest.mark.unit
class RiskBasedSizingTests(unittest.TestCase):
    def test_risk_based_positive_result(self) -> None:
        sizer = PositionSizer(SIZING_MODE_RISK_BASED)
        # entry=100, stop=95 → risk_distance=5; result should be positive
        margin = sizer.margin_to_use(
            _make_inputs(available_balance=200.0, entry_price=100.0, stop_price=95.0)
        )
        self.assertGreater(margin, 0.0)

    def test_risk_based_zero_stop_distance(self) -> None:
        sizer = PositionSizer(SIZING_MODE_RISK_BASED)
        margin = sizer.margin_to_use(_make_inputs(entry_price=100.0, stop_price=100.0))
        self.assertEqual(margin, 0.0)

    def test_risk_based_zero_balance(self) -> None:
        sizer = PositionSizer(SIZING_MODE_RISK_BASED)
        margin = sizer.margin_to_use(_make_inputs(available_balance=0.0))
        self.assertEqual(margin, 0.0)

    def test_risk_based_zero_entry_price(self) -> None:
        sizer = PositionSizer(SIZING_MODE_RISK_BASED)
        margin = sizer.margin_to_use(_make_inputs(entry_price=0.0))
        self.assertEqual(margin, 0.0)

    def test_risk_based_capped_at_usable_balance(self) -> None:
        sizer = PositionSizer(SIZING_MODE_RISK_BASED)
        # Very small risk distance → very large position → capped at available_balance
        margin = sizer.margin_to_use(
            _make_inputs(available_balance=100.0, entry_price=100.0, stop_price=99.99)
        )
        self.assertLessEqual(margin, 100.0)


@pytest.mark.unit
class IsEntrySizeValidTests(unittest.TestCase):
    def test_valid_qty_and_notional(self) -> None:
        self.assertTrue(is_entry_size_valid(0.1, 100.0, 0.01, 5.0))

    def test_zero_qty_invalid(self) -> None:
        self.assertFalse(is_entry_size_valid(0.0, 100.0, 0.0, 0.0))

    def test_negative_qty_invalid(self) -> None:
        self.assertFalse(is_entry_size_valid(-0.1, 100.0, 0.0, 0.0))

    def test_zero_price_invalid(self) -> None:
        self.assertFalse(is_entry_size_valid(0.1, 0.0, 0.0, 0.0))

    def test_below_min_qty_invalid(self) -> None:
        self.assertFalse(is_entry_size_valid(0.001, 100.0, 0.01, 0.0))

    def test_below_min_notional_invalid(self) -> None:
        # 0.001 * 100 = 0.1 < 5.0
        self.assertFalse(is_entry_size_valid(0.001, 100.0, 0.0, 5.0))

    def test_zero_min_qty_no_min_qty_check(self) -> None:
        # min_qty=0 disables qty floor
        self.assertTrue(is_entry_size_valid(0.001, 1000.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
