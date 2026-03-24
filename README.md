# Binance Futures Trading Bot

Algorithmic bot for Binance USDT-M perpetual futures with:
- REST scheduler over closed candles (no websocket dependency)
- EMA pullback long-only strategy shared by live and backtest
- Strict TP/SL monitor lifecycle with breakeven and ATR trailing
- Paper and live trading support

## Current Defaults

| Setting | Value |
|---------|-------|
| Symbol universe | Top **300** USDT perpetual symbols by 24h quote volume (hardcoded in `config.py`) |
| Evaluation intervals | `15m` (main) + `1h` (context) |
| Max concurrent positions | `2` |
| Sizing mode | `pct_balance` — **5% of available balance** per position |
| SELL filter | SELL signals blocked on `4h` interval (`block_sell_on_intervals`) |
| Loss scaling | Implemented but disabled by default (`enable_loss_scaling=False`) |

## Architecture

Core modules:
- `main.py` — orchestration (bootstrap, scheduler, shutdown, heartbeat)
- `config.py` — single source of runtime settings and `.env` parsing
- `indicators.py` — shared EMA / ATR / RSI helpers
- `strategy.py` — configurable `evaluate_signal(...)` used by live and backtest
- `execution.py` — order routing, rounding, TP/SL placement, OCO monitor loop
- `monitor.py` — position supervision (`PositionMonitor`) and orphan recovery
- `data_stream.py` — REST candle polling scheduler + in-memory cache
- `risk.py` — thread-safe `RiskManager`
- `sizing.py` — position sizing policies (`pct_balance`, `fixed_margin`, `risk_based`)

Service layer:
- `services/bootstrap_service.py` — symbol loading and executor setup
- `services/signal_service.py` — signal evaluation per interval
- `services/entry_service.py` — signal gating, entry execution, monitor spawn
- `services/position_service.py` — position cache, orphan recovery, balance helpers
- `services/telegram_service.py` — alert formatting and delivery

Backtest:
- `backtest/backtest.py` — parallel downloader + candle-by-candle simulator

## Sizing Policy

Controlled by `SIZING_MODE` in `.env` (default is hardcoded in `config.py`):

| Mode | Behaviour |
|------|-----------|
| `pct_balance` *(default)* | `margin = available_balance × RISK_PER_TRADE_PCT` (e.g. 100 USDT × 5% = 5 USDT) |
| `fixed_margin` | Flat `FIXED_MARGIN_PER_TRADE_USDT` per trade |
| `risk_based` | Sizes by risk budget derived from stop distance and `MARGIN_UTILIZATION` |

Leverage is applied on top: `notional = margin × leverage`.

## Configuration

Copy and edit:
```bash
cp .env.example .env
```

Minimum required keys:
```env
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true        # set false only for live capital
USE_PAPER_TRADING=true      # set false only for live capital
```

Other relevant settings (all have safe defaults in `config.py`):

| Variable | Description |
|----------|-------------|
| `RISK_PER_TRADE_PCT` | Fraction of balance used as margin per trade (default `0.05`) |
| `SIZING_MODE` | `pct_balance` / `fixed_margin` / `risk_based` |
| `MAX_POSITIONS` | Max simultaneous open positions |
| `COOLDOWN_SEC` | Seconds between entries |
| `DAILY_DRAWDOWN_LIMIT_USDT` | Max daily loss before bot pauses |
| `BLOCK_SELL_ON_INTERVALS` | Comma-separated intervals where SELL signals are suppressed (default `4h`) |
| `ENABLE_LOSS_SCALING` | Enable DCA on losing positions — **only after exhaustive backtest** (default `false`) |
| `MAIN_INTERVAL` / `CONTEXT_INTERVAL` | Candle intervals for signal and HTF confirmation |

> **Note:** `TOP_VOLUME_SYMBOLS_COUNT` and `TOP_SYMBOLS_LIMIT` are hardcoded to **300** in `config.py` and cannot be overridden via `.env`.

## Run

```bash
python main.py
```

Paper mode — set in `.env`:
```env
USE_PAPER_TRADING=true
PAPER_START_BALANCE=100
```

Live mode — set in `.env`:
```env
BINANCE_TESTNET=false
USE_PAPER_TRADING=false
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
```

## Backtest

```bash
python backtest/backtest.py
```

Results are written to `backtest/results/`.

## Docker

```bash
docker compose up -d --build
```

Healthcheck is based on `logs/.alive` updated by the heartbeat loop.

## Notes

- Orphan open positions (opened before bot restart) are automatically recovered on startup in live mode.
- TP/SL orders are placed on-exchange and survive bot restarts.
- Scheduler callbacks fire per closed candle and evaluate all 300 symbols in parallel.
- Telegram alerts are best-effort and rate-limited.
