"""Signal engine for aggressive M15 continuation entries.

Design goals:
- High signal throughput across a broad symbol universe.
- Strict 1H directional alignment to avoid trading against bias.
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
RANGE_CROSS_LOOKBACK = 12
RANGE_MAX_CROSSES = 3
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
    - Strict 1H trend filter using EMA50 position and EMA50 slope.
    - Simplified aggressive M15 continuation trigger.
    - Relaxed volume confirmation (`>= 0.8 * avg5`).

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
    h1_last = h1.iloc[-1]
    h1_prev = h1.iloc[-2]

    required = [
        last["ema7"],
        last["ema25"],
        last["dif"],
        last["vol_avg5_prev"],
        last["atr"],
        h1_last["ema50"],
        h1_prev["ema50"],
        last["atr"],
    ]
    if any(pd.isna(v) for v in required):
        return None

    price = float(last["close"])
    if price <= 0:
        return None

    # Strict 1H trend alignment.
    h1_close = float(h1_last["close"])
    h1_ema_last = float(h1_last["ema50"])
    h1_ema_prev = float(h1_prev["ema50"])
    bias_long = h1_close > h1_ema_last and h1_ema_last > h1_ema_prev
    bias_short = h1_close < h1_ema_last and h1_ema_last < h1_ema_prev

    vol_avg5 = float(last["vol_avg5_prev"] or 0.0)
    vol_confirm_ok = vol_avg5 > 0 and float(last["volume"]) >= (vol_avg5 * 0.8)
    if not vol_confirm_ok:
        return None

    # Simplified aggressive continuation entries.
    long_impulse = (
        float(last["ema7"]) > float(last["ema25"])
        and price > float(last["ema7"])
        and float(last["dif"]) > 0
        and float(last["close"]) > float(prev1["high"])
    )
    short_impulse = (
        float(last["ema7"]) < float(last["ema25"])
        and price < float(last["ema7"])
        and float(last["dif"]) < 0
        and float(last["close"]) < float(prev1["low"])
    )

    breakout_ts = last.get("close_time")
    if isinstance(breakout_ts, pd.Timestamp):
        breakout_time = breakout_ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        breakout_time = str(breakout_ts)

    atr_val = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
    atr_avg = float(m15["atr"].rolling(window=20).mean().iloc[-1]) if len(m15) >= 25 else 0.0
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
