"""Signal engine for conservative M15 continuation entries.

Design goals:
- Reduce low-quality breakouts across a broad symbol universe.
- Enforce strict 1H directional/trend-strength alignment.
- Keep output schema stable for `main.py` and downstream execution code.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

EMA_FAST = 7
EMA_MID = 25
EMA_BIAS_1H = 50
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Retained legacy constants for compatibility and potential toggles.
MAX_MOVE_WITHOUT_PULLBACK = 0.018  # 1.8%
MIN_DISTANCE_TO_LEVEL = 0.01  # 1%
VOL_CONFIRM_WINDOW = 5
RANGE_MAX_CROSSES = 2
RANGE_CROSS_LOOKBACK = 15
SWING_LOOKBACK = 8
MIN_RR_TARGET = 1.8


def _ema(series: pd.Series, period: int) -> pd.Series:
    """Compute exponential moving average for a price series."""
    return series.ewm(span=period, adjust=False).mean()


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return MACD tuple: DIF, DEA (signal), and histogram."""
    ema_fast = close.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=MACD_SLOW, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=MACD_SIGNAL, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Compute ATR using an EWMA of true range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
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


def _is_pivot_high(high: pd.Series, idx: int, wing: int = 2) -> bool:
    """Check if `idx` is a local pivot high in a symmetric window."""
    val = float(high.iloc[idx])
    left = high.iloc[idx - wing:idx]
    right = high.iloc[idx + 1:idx + 1 + wing]
    if left.empty or right.empty:
        return False
    return bool((val >= left.max()) and (val >= right.max()))


def _is_pivot_low(low: pd.Series, idx: int, wing: int = 2) -> bool:
    """Check if `idx` is a local pivot low in a symmetric window."""
    val = float(low.iloc[idx])
    left = low.iloc[idx - wing:idx]
    right = low.iloc[idx + 1:idx + 1 + wing]
    if left.empty or right.empty:
        return False
    return bool((val <= left.min()) and (val <= right.min()))


def _extract_levels(df: pd.DataFrame, lookback: int = 180) -> tuple[list[float], list[float]]:
    """Extract support/resistance candidates from pivot highs/lows."""
    if df.empty or len(df) < 12:
        return [], []
    w = df.iloc[-lookback:].copy() if len(df) > lookback else df.copy()
    highs = w["high"].reset_index(drop=True)
    lows = w["low"].reset_index(drop=True)
    resistances: list[float] = []
    supports: list[float] = []
    for i in range(2, len(w) - 2):
        if _is_pivot_high(highs, i):
            resistances.append(float(highs.iloc[i]))
        if _is_pivot_low(lows, i):
            supports.append(float(lows.iloc[i]))
    if not resistances:
        resistances.append(float(highs.max()))
    if not supports:
        supports.append(float(lows.min()))
    return resistances, supports


def _nearest_above(price: float, levels: list[float]) -> float | None:
    """Return nearest level above `price`."""
    cands = [x for x in levels if x > price]
    return min(cands) if cands else None


def _nearest_below(price: float, levels: list[float]) -> float | None:
    """Return nearest level below `price`."""
    cands = [x for x in levels if x < price]
    return max(cands) if cands else None


def _is_flat_range(ema_fast: pd.Series, ema_mid: pd.Series) -> bool:
    """Detect frequent EMA crossover behavior often associated with ranges."""
    if len(ema_fast) < RANGE_CROSS_LOOKBACK or len(ema_mid) < RANGE_CROSS_LOOKBACK:
        return True
    diff = (ema_fast - ema_mid).iloc[-RANGE_CROSS_LOOKBACK:]
    sign = diff > 0
    crosses = int((sign != sign.shift(1)).sum())
    return crosses >= RANGE_MAX_CROSSES


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
    """Evaluate one symbol and return a normalized signal payload.

    Current ruleset:
    - Strict 1H trend alignment with EMA50 slope and 1H MACD DIF direction.
    - Conservative M15 continuation with mandatory pullback structure.
    - Strong anti-chop, anti-climax, and volume quality gates.

    Parameters are kept to preserve the shared strategy interface used by
    `main.py`, even when some knobs are not used by this implementation.
    """
    del ema_trend, ema_fast, ema_mid, atr_avg_window, rsi_period
    del rsi_long_min, rsi_long_max, rsi_short_min, rsi_short_max, volume_min_ratio
    del volume_avg_window

    if main_df.empty or context_df.empty:
        return None
    if len(main_df) < 60 or len(context_df) < 60:
        return None

    m15 = main_df.copy()
    h1 = context_df.copy()

    m15["ema7"] = _ema(m15["close"], EMA_FAST)
    m15["ema25"] = _ema(m15["close"], EMA_MID)
    m15["atr"] = _atr(m15, atr_period)
    m15["vol_avg5_prev"] = m15["volume"].rolling(window=VOL_CONFIRM_WINDOW).mean().shift(1)

    dif, dea, hist = _macd(m15["close"])
    m15["dif"] = dif
    m15["dea"] = dea
    m15["hist"] = hist

    h1["ema50"] = _ema(h1["close"], EMA_BIAS_1H)
    h1_dif, _, _ = _macd(h1["close"])
    h1["dif"] = h1_dif

    last = m15.iloc[-1]
    prev1 = m15.iloc[-2]
    prev2 = m15.iloc[-3]
    h1_last = h1.iloc[-1]
    h1_prev = h1.iloc[-2]

    required = [
        last["ema7"],
        last["ema25"],
        last["dif"],
        last["vol_avg5_prev"],
        last["atr"],
        last["open"],
        last["high"],
        last["low"],
        prev1["high"],
        prev1["low"],
        prev1["open"],
        prev1["close"],
        prev1["volume"],
        prev1["ema25"],
        prev2["volume"],
        h1_last["ema50"],
        h1_prev["ema50"],
        h1_last["dif"],
    ]
    if any(pd.isna(v) for v in required):
        return None

    price = float(last["close"])
    if price <= 0:
        return None

    # Strong range filter to suppress choppy regimes.
    if _is_flat_range(m15["ema7"], m15["ema25"]):
        return None

    # Strict 1H trend alignment.
    h1_close = float(h1_last["close"])
    h1_ema_last = float(h1_last["ema50"])
    h1_ema_prev = float(h1_prev["ema50"])
    h1_dif_last = float(h1_last["dif"])
    bias_long = (
        h1_close > h1_ema_last
        and h1_ema_last > h1_ema_prev
        and h1_dif_last > 0
    )
    bias_short = (
        h1_close < h1_ema_last
        and h1_ema_last < h1_ema_prev
        and h1_dif_last < 0
    )
    if not (bias_long or bias_short):
        return None

    atr_val = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
    atr_avg = float(m15["atr"].rolling(window=20).mean().iloc[-1]) if len(m15) >= 25 else 0.0
    if atr_val <= 0 or atr_avg <= 0:
        return None

    # Block climactic candles.
    candle_range = float(last["high"] - last["low"])
    if candle_range <= 0:
        return None
    if candle_range > (2.2 * atr_val):
        return None

    # Volume filter.
    vol_avg5 = float(last["vol_avg5_prev"] or 0.0)
    vol_last = float(last["volume"])
    vol_confirm_ok = vol_avg5 > 0 and vol_last >= vol_avg5
    if not vol_confirm_ok:
        return None

    # Reject isolated volume spikes without continuation quality.
    prev1_vol = float(prev1["volume"])
    prev2_vol = float(prev2["volume"])
    isolated_spike = (
        vol_avg5 > 0
        and vol_last >= (vol_avg5 * 2.5)
        and prev1_vol < vol_avg5
        and prev2_vol < vol_avg5
    )
    if isolated_spike:
        return None

    prev1_open = float(prev1["open"])
    prev1_close = float(prev1["close"])
    prev1_high = float(prev1["high"])
    prev1_low = float(prev1["low"])
    prev1_ema25 = float(prev1["ema25"])

    # Core continuation direction logic with required pullback structure.
    ema7_last = float(last["ema7"])
    ema25_last = float(last["ema25"])

    long_impulse = (
        ema7_last > ema25_last
        and prev1_close < prev1_open
        and prev1_low >= prev1_ema25
        and price > prev1_high
        and price > ema7_last
        and float(last["dif"]) > 0
    )
    short_impulse = (
        ema7_last < ema25_last
        and prev1_close > prev1_open
        and prev1_high <= prev1_ema25
        and price < prev1_low
        and price < ema7_last
        and float(last["dif"]) < 0
    )

    breakout_ts = last.get("close_time")
    if isinstance(breakout_ts, pd.Timestamp):
        breakout_time = breakout_ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        breakout_time = str(breakout_ts)

    swing_w = m15.iloc[-(SWING_LOOKBACK + 1):-1]

    if bias_long and long_impulse:
        swing_low = float(swing_w["low"].min()) if not swing_w.empty else float(prev1["low"])
        stop_price = swing_low
        risk_per_unit = price - stop_price
        if risk_per_unit <= 0:
            return None
        return {
            "side": "BUY",
            "price": price,
            "atr": atr_val,
            "atr_avg": atr_avg,
            "risk_per_unit": risk_per_unit,
            "rr_target": MIN_RR_TARGET,
            "stop_price": stop_price,
            "tp_price": price + (risk_per_unit * MIN_RR_TARGET),
            "estructura_valida": True,
            "retroceso_valido": True,
            "volumen_confirmado": True,
            "structure_ok": True,
            "volume_ok": True,
            "confirm_m15": "EMA7>EMA25 + close>EMA7 + DIF>0 + cierre sobre maximo previo",
            "breakout_time": breakout_time,
        }

    if bias_short and short_impulse:
        swing_high = float(swing_w["high"].max()) if not swing_w.empty else float(prev1["high"])
        stop_price = swing_high
        risk_per_unit = stop_price - price
        if risk_per_unit <= 0:
            return None
        return {
            "side": "SELL",
            "price": price,
            "atr": atr_val,
            "atr_avg": atr_avg,
            "risk_per_unit": risk_per_unit,
            "rr_target": MIN_RR_TARGET,
            "stop_price": stop_price,
            "tp_price": price - (risk_per_unit * MIN_RR_TARGET),
            "estructura_valida": True,
            "retroceso_valido": True,
            "volumen_confirmado": True,
            "structure_ok": True,
            "volume_ok": True,
            "confirm_m15": "EMA7<EMA25 + close<EMA7 + DIF<0 + cierre bajo minimo previo",
            "breakout_time": breakout_time,
        }

    return None
