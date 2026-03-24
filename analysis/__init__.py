"""Analysis package — pure, testable metric and regime helpers.

All functions in this package are stateless and have no dependency on the
live runtime, Binance API, or any I/O. They operate on trade dicts produced
by backtest/backtest.py and are safe to import in tests or scripts.

Modules:
  metrics — compute_stats, top_winner_concentration, rolling_windows,
             oos_split, segment_trades
  regime  — classify_ema_regime, classify_volatility, regime_analysis
"""
