"""Technical indicator enrichment helpers.

This module adds derived columns to OHLCV dataframes and keeps the original
market data untouched by working on a copy.
"""
from __future__ import annotations

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volume import VolumeWeightedAveragePrice


def add_indicators(
    df: pd.DataFrame,
    ema_fast: int,
    ema_slow: int,
    ema_trend: int,
    rsi_period: int,
    vwap_window: int,
) -> pd.DataFrame:
    """Return a dataframe enriched with EMA, RSI, VWAP, and volume flags.

    Expected input columns: `open`, `high`, `low`, `close`, `volume`.
    """
    out = df.copy()

    out["ema_fast"] = EMAIndicator(out["close"], window=ema_fast).ema_indicator()
    out["ema_slow"] = EMAIndicator(out["close"], window=ema_slow).ema_indicator()
    out["ema_trend"] = EMAIndicator(out["close"], window=ema_trend).ema_indicator()

    out["rsi"] = RSIIndicator(out["close"], window=rsi_period).rsi()

    vwap = VolumeWeightedAveragePrice(
        high=out["high"],
        low=out["low"],
        close=out["close"],
        volume=out["volume"],
        window=vwap_window,
    )
    out["vwap"] = vwap.volume_weighted_average_price()

    out["volume_prev"] = out["volume"].shift(1)
    out["volume_increase"] = out["volume"] > out["volume_prev"]

    return out
