"""Risk state tracking and trade throttling primitives.

The logic in this module is intentionally side-effect free except for updates
to in-memory state, which makes it safe to call on every candle close.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd


@dataclass
class RiskState:
    """Mutable runtime state used by `RiskManager` decision rules."""

    consecutive_losses: int = 0
    last_trade_time: datetime | None = None
    day_start_equity: float = 0.0
    current_day: datetime | None = None
    equity: float = 0.0
    paused: bool = False
    loss_pause_until: datetime | None = None


@dataclass
class RiskManager:
    """Encapsulates cooldown and daily loss guards.

    The caller controls when `can_trade` and `update_trade` are invoked.
    This class does not place orders or read market data from exchanges.
    """

    cooldown_sec: int
    max_consecutive_losses: int
    daily_drawdown_limit: float
    daily_drawdown_limit_usdt: float
    loss_pause_sec: int
    volatility_pause: bool
    volatility_threshold: float
    state: RiskState = field(default_factory=RiskState)

    def init_equity(self, equity: float) -> None:
        """Initialize day/equity baselines at process startup."""
        now = datetime.now(timezone.utc)
        self.state.equity = equity
        self.state.day_start_equity = equity
        self.state.current_day = now.date()

    def _roll_day(self, now: datetime) -> None:
        """Reset day-scoped counters when UTC date changes."""
        if self.state.current_day != now.date():
            self.state.current_day = now.date()
            self.state.day_start_equity = self.state.equity
            self.state.consecutive_losses = 0
            self.state.paused = False

    def can_trade(self, now: datetime) -> bool:
        """Return whether a new trade may be opened at `now`."""
        self._roll_day(now)

        if self.state.paused:
            return False

        if self.state.loss_pause_until and now < self.state.loss_pause_until:
            return False
        if self.state.loss_pause_until and now >= self.state.loss_pause_until:
            self.state.loss_pause_until = None

        if self.state.last_trade_time:
            elapsed = (now - self.state.last_trade_time).total_seconds()
            if elapsed < self.cooldown_sec:
                return False

        if self.state.consecutive_losses >= self.max_consecutive_losses:
            self.state.loss_pause_until = now + timedelta(seconds=max(0, self.loss_pause_sec))
            self.state.consecutive_losses = 0
            return False

        drawdown = 0.0
        if self.state.day_start_equity > 0:
            drawdown = (self.state.day_start_equity - self.state.equity) / self.state.day_start_equity
        if drawdown >= self.daily_drawdown_limit:
            self.state.paused = True
            return False
        dd_usdt = self.state.day_start_equity - self.state.equity
        if dd_usdt >= self.daily_drawdown_limit_usdt:
            self.state.paused = True
            return False

        return True

    def update_trade(self, pnl: float, now: datetime) -> None:
        """Apply realized PnL and update post-trade throttling counters."""
        self._roll_day(now)
        self.state.equity += pnl
        self.state.last_trade_time = now
        if pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

    def volatility_ok(self, df: pd.DataFrame) -> bool:
        """Check optional single-candle volatility guard."""
        if not self.volatility_pause:
            return True
        if df.empty:
            return False
        last = df.iloc[-1]
        if last["close"] <= 0:
            return False
        candle_range = (last["high"] - last["low"]) / last["close"]
        return candle_range <= self.volatility_threshold


def calc_margin_to_use(available_balance: float, utilization: float = 0.95) -> float:
    """Convert available balance into a bounded margin budget."""
    if utilization < 0.6:
        utilization = 0.6
    if utilization > 0.95:
        utilization = 0.95
    return max(0.0, available_balance * utilization)
