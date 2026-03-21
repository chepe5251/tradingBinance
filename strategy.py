"""EMA Pullback Long-Only signal engine — v2 (backtest-optimized).

Detects high-probability pullback entries by waiting for price to retrace
to EMA20 within a well-aligned EMA20/50/200 uptrend, then requiring a
bullish rejection candle followed by a break-of-high confirmation candle.

This version is LONG-ONLY. Shorts were removed after backtesting showed
205 short trades at 35.5% WR and -18.12 USDT net PnL across all timeframes.

Key backtest findings that shaped the filters:
  - Vol >1.5x avg: exhaustion/liquidation spikes — filtered out
  - RSI <48 at signal: 28.7% WR, actual weakness — filtered out
  - EMA spread >1.0 ATR: overextended trend, pullbacks don't bounce — filtered out
  - Score <1.5: too many marginal setups — filtered out

Score breakdown (max ~4.0):
  2.0  — body quality   (body_ratio vs MIN_BODY_RATIO baseline)
  1.0  — RSI sweet spot (RSI in 53-63 zone = 1.0, otherwise 0)
  1.0  — EMA spread     (EMA20-EMA50 separation relative to ATR, capped at 1.0)
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

EMA_FAST               = 20
EMA_MID                = 50
EMA_SLOW               = 200
RSI_PERIOD             = 14
VOL_LOOKBACK           = 20
ATR_PERIOD             = 14
MIN_VOL_MULT           = 1.05
MAX_VOL_MULT           = 1.5
RSI_LONG_MIN           = 48.0
RSI_LONG_MAX           = 68.0
MIN_BODY_RATIO         = 0.35
RR_TARGET              = 2.0
MIN_RISK_ATR           = 0.5
MAX_RISK_ATR           = 3.0
PULLBACK_TOLERANCE_ATR = 0.8
MIN_EMA_SPREAD_ATR     = 0.15
MAX_EMA_SPREAD_ATR     = 1.0
MIN_SCORE              = 1.5


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def evaluate_signal(
    main_df: pd.DataFrame,
    context_df: pd.DataFrame,
    ema_trend: int,
    ema_fast: int,
    ema_mid: int,
    atr_period: int,
    atr_avg_window: int,
    volume_avg_window: int,
    rsi_period: int,
    rsi_long_min: float,
    rsi_long_max: float,
    rsi_short_min: float,
    rsi_short_max: float,
    volume_min_ratio: float,
) -> Optional[dict]:
    """Evaluate one symbol for an EMA Pullback Long entry.

    Requires at least 230 candles so EMA200 is meaningful.
    context_df and most parameters are accepted for API compatibility
    but this strategy uses the fixed constants defined at module level.
    """
    del (
        ema_trend, ema_fast, ema_mid, atr_avg_window, volume_avg_window,
        rsi_period, rsi_long_min, rsi_long_max, rsi_short_min, rsi_short_max,
        volume_min_ratio, context_df,
    )

    if main_df.empty or len(main_df) < 230:
        return None

    df = main_df.copy()
    if "ema20" not in df.columns:
        df["ema20"]   = _ema(df["close"], EMA_FAST)
        df["ema50"]   = _ema(df["close"], EMA_MID)
        df["ema200"]  = _ema(df["close"], EMA_SLOW)
        df["atr"]     = _atr(df, ATR_PERIOD)
        df["avg_vol"] = df["volume"].rolling(VOL_LOOKBACK).mean()
        df["rsi"]     = _rsi(df["close"], RSI_PERIOD)

    if len(df) < 3:
        return None

    # ── extract candles ───────────────────────────────────────────────────────
    sig  = df.iloc[-2]   # signal candle  — shows pullback + rejection
    conf = df.iloc[-1]   # confirmation candle — just closed, confirms direction
    prev = df.iloc[-3]   # candle before signal

    s_open    = float(sig["open"])
    s_close   = float(sig["close"])
    s_high    = float(sig["high"])
    s_low     = float(sig["low"])
    s_vol     = float(sig["volume"])
    s_ema20   = float(sig["ema20"])
    s_ema50   = float(sig["ema50"])
    s_ema200  = float(sig["ema200"])
    s_atr     = float(sig["atr"])
    s_avg_vol = float(sig["avg_vol"])
    s_rsi     = float(sig["rsi"])

    c_open  = float(conf["open"])
    c_close = float(conf["close"])
    c_high  = float(conf["high"])
    c_low   = float(conf["low"])

    p_close = float(prev["close"])
    p_ema20 = float(prev["ema20"])

    # ── NaN / validity checks ─────────────────────────────────────────────────
    required = [
        s_open, s_close, s_high, s_low, s_vol,
        s_ema20, s_ema50, s_ema200, s_atr, s_avg_vol, s_rsi,
        c_open, c_close, c_high, c_low,
        p_close, p_ema20,
    ]
    if any(v != v for v in required):   # NaN != NaN
        return None

    if s_atr <= 0 or s_avg_vol <= 0:
        return None

    rng = s_high - s_low
    if rng <= 0:
        return None

    body        = abs(s_close - s_open)
    body_ratio  = body / rng
    entry_price = c_close

    ts = conf.get("close_time")
    timestamp = (
        ts.strftime("%Y-%m-%d %H:%M:%S UTC")
        if isinstance(ts, pd.Timestamp)
        else str(ts)
    )

    # ── LONG setup ────────────────────────────────────────────────────────────
    # 1. Structural uptrend: EMA20 > EMA50 > EMA200
    if not (s_ema20 > s_ema50 and s_ema50 > s_ema200):
        return None

    spread     = s_ema20 - s_ema50
    spread_atr = spread / s_atr

    # 2. Minimum EMA separation — filters flat/ranging markets
    if spread_atr < MIN_EMA_SPREAD_ATR:
        return None

    # 3. Trend not overextended — spread >1.0 ATR = pullbacks don't bounce
    if spread_atr > MAX_EMA_SPREAD_ATR:
        return None

    # 4. Price pulled back to EMA20 (signal candle low within tolerance band)
    tol = PULLBACK_TOLERANCE_ATR * s_atr
    if not (s_low <= s_ema20 + tol and s_low >= s_ema20 - tol):
        return None

    # 5. Did not break EMA50 — structure intact
    if s_close <= s_ema50:
        return None

    # 6. RSI in healthy pullback zone — not weak, not overbought
    if not (RSI_LONG_MIN <= s_rsi <= RSI_LONG_MAX):
        return None

    # 7. Bullish rejection candle closing in upper third of its range
    upper_third = s_low + (2 / 3) * rng
    if not (body_ratio >= MIN_BODY_RATIO and s_close > s_open and s_close > upper_third):
        return None

    # 8. Volume in optimal range — confirms interest without exhaustion spike
    if not (s_vol >= MIN_VOL_MULT * s_avg_vol and s_vol <= MAX_VOL_MULT * s_avg_vol):
        return None

    # 9. Confirmation candle breaks above signal candle high
    if c_close <= s_high:
        return None

    # ── levels ────────────────────────────────────────────────────────────────
    stop_price = s_low - (0.1 * s_atr)
    risk       = entry_price - stop_price
    if risk < MIN_RISK_ATR * s_atr or risk > MAX_RISK_ATR * s_atr:
        return None

    tp_price = entry_price + risk * RR_TARGET

    # ── score ─────────────────────────────────────────────────────────────────
    score = round(
        min(2.0, ((body_ratio - MIN_BODY_RATIO) / (1 - MIN_BODY_RATIO)) * 2)
        + (1.0 if (RSI_LONG_MIN + 5) < s_rsi < (RSI_LONG_MAX - 5) else 0)
        + min(1.0, (spread_atr - MIN_EMA_SPREAD_ATR) * 2),
        2,
    )

    if score < MIN_SCORE:
        return None

    return {
        "side":          "BUY",
        "price":         entry_price,
        "stop_price":    stop_price,
        "tp_price":      tp_price,
        "risk_per_unit": risk,
        "rr_target":     RR_TARGET,
        "atr":           float(s_atr),
        "score":         score,
        "strategy":      "ema_pullback_long",
        "confirm_m15":   (
            f"EMA20 pullback at {s_ema20:.4f} | "
            f"body={body_ratio:.2f} | "
            f"vol={s_vol/s_avg_vol:.1f}x | "
            f"rsi={s_rsi:.1f} | "
            f"spread={spread_atr:.2f}atr | "
            f"confirm close={c_close:.4f}"
        ),
        "breakout_time": timestamp,
    }
