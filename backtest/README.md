# Backtest

`backtest/backtest.py` downloads Binance Futures klines, simulates trades candle-by-candle, and writes:
- `backtest/results/backtest_*.csv`
- `backtest/results/analysis_*.csv`
- `backtest/results/equity_*.csv`

## Key behavior
- Uses the same `strategy.evaluate_signal(...)` logic as live runtime
- Loads strategy and interval defaults from `config.py` via `.env`
- Symbol universe: top **300** USDT perpetual symbols by 24h quote volume (hardcoded in `config.py`)

## Run
From repository root:
```bash
python backtest/backtest.py
```

## Core parameters
- `TOP_SYMBOLS`: fixed at **300** (hardcoded; `TOP_VOLUME_SYMBOLS_COUNT` / `TOP_SYMBOLS_LIMIT` cannot be overridden via `.env`)
- `INTERVALS`: derived from `MAIN_INTERVAL`, `CONTEXT_INTERVAL`, and higher timeframe map
- `CANDLES_PER_INTERVAL`: derived from `HISTORY_CANDLES_MAIN` and `HISTORY_CANDLES_CONTEXT` with backtest-safe minimums
- `SIZING_MODE`: default `pct_balance` — each simulated trade uses `RISK_PER_TRADE_PCT` of the running balance as margin
- `LEVERAGE`: `LEVERAGE`

## Notes
- SELL trades are blocked on intervals listed in `BLOCK_SELL_ON_INTERVALS` (default `4h`) to mirror live long-only behavior.
- `ENABLE_LOSS_SCALING=false` by default; DCA scaling is not applied during simulation unless explicitly enabled.
- Rate limiter enforces Binance weight budget during parallel downloads.
