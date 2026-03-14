# Binance Futures Scalping Bot (USDT-M)

Algorithmic trading bot for **Binance USDT-M Futures** that scans the full
perpetual universe, broadcasts signals via Telegram, and executes one trade at
a time with automatic TP/SL protection.

> **Warning:** This software opens and closes real positions. Start in
> `testnet` or `paper` mode before deploying real capital.

---

## Core Features

- Full USDT-M perpetual symbol universe (529+ pairs by default).
- Signal engine on **M15** with strict **1H** trend alignment.
- All valid signals broadcast to Telegram.
- Executes only the **top-scored** signal when `RiskManager` allows and no open position exists.
- Limit entry with automatic market fallback on timeout.
- Mandatory TP/SL with recovery logic if protection orders disappear.
- Loss-based scaling: up to **5 scale-in levels** on an adverse move.
- Telegram rate-limit handling (`HTTP 429` retry).
- WebSocket multiplexer with stale-detection and automatic restart.

---

## Strategy: Liquidity Sweep Reversal (M15)

### Overview

The strategy detects **liquidity sweeps** — candles that break a key 20-bar
high or low but close back inside the prior range, signalling that the
breakout was absorbed by the market.  A second closed candle is required to
confirm the reversal before any signal is emitted.

This approach targets high-probability counter-moves after stop-hunts,
entering after confirmation and placing the stop at the swept extreme.

### Signal Generation — LONG

All conditions must pass in order. First failure = no signal.

| # | Rule | Condition |
|---|------|-----------|
| 1 | **Trend bullish** | Sweep candle `close > EMA200` AND `EMA50 > EMA200` |
| 2 | **Bearish sweep** | Sweep candle `low < lowest low of previous 20 candles` |
| 3 | **False breakout** | Sweep candle `close > lowest_low_20` (price rejected the break) |
| 4 | **Absorption wick** | `lower_wick / range ≥ 0.6` (strong buying tail) |
| 5 | **Volume confirmation** | Sweep candle `volume ≥ 1.3 × avg volume (20)` |
| 6 | **Size filter** | Sweep candle `range < 2 × ATR` |
| 7 | **Reversal confirmation** | Next closed candle: `high > sweep high` AND `close > sweep close` |
| 8 | **Risk validity** | `risk_per_unit ≥ 0.5 × ATR` |

- **Entry:** close of the confirmation candle
- **Stop loss:** low of the sweep candle
- **Take profit:** `entry + risk × 2.0`

### Signal Generation — SHORT

Exact mirror:
- `close < EMA200` AND `EMA50 < EMA200`
- Sweep candle `high > highest_high_20`, closes back below it
- `upper_wick / range ≥ 0.6`
- Confirmation candle: `low < sweep low` AND `close < sweep close`
- **Stop loss:** high of the sweep candle

### Score System

| Component | Formula | Max |
|-----------|---------|-----|
| Wick quality | `(wick_ratio − 0.6) / 0.4 × 3` | 3.0 |
| Volume boost | `vol / avg_vol − 1.3` | 2.0 |

Signals with stronger absorption wicks and higher relative volume rank higher.
When multiple symbols generate valid signals simultaneously, only the
**highest-scoring** signal is executed.

---

## Loss-Based Scaling

After the initial entry, the bot can scale in up to **5 additional levels** when
the position moves against you, lowering the average entry price:

| Level | Trigger (loss on margin) | Additional margin |
|-------|--------------------------|------------------|
| 1 | −50% | $5 |
| 2 | −100% | $10 |
| 3 | −200% | $20 |
| 4 | −400% | $40 |
| 5 | −800% | $80 |

Scale levels are configured via `SCALE_LEVEL*_MARGIN_USDT` env vars. Set to
`0` to disable a level.

---

## Architecture

| File | Responsibility |
|------|---------------|
| `main.py` | Orchestration: stream, signals, execution, monitoring |
| `strategy.py` | Signal engine (filters, scoring, TP/SL calculation) |
| `execution.py` | Order placement, Binance filter rounding, TP/SL, OCO monitor |
| `data_stream.py` | Historical candle load + WebSocket multiplexer + cache |
| `risk.py` | Cooldown, daily drawdown guard, consecutive-loss pause |
| `config.py` | `Settings` dataclass and `.env` loader |
| `test_trade.py` | Manual script to validate minimal order placement |

---

## Requirements

- Python 3.10+
- Binance Futures account (testnet or live)

```bash
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the project root:

```env
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# Trading endpoint
BINANCE_TESTNET=true
BINANCE_DATA_TESTNET=false

# Optional: Telegram alerts
TELEGRAM_BOT_TOKEN=xxxxxxxx
TELEGRAM_CHAT_ID=123456789

# Optional: simulated trading
USE_PAPER_TRADING=false
PAPER_START_BALANCE=25

# Risk controls
FIXED_MARGIN_PER_TRADE_USDT=5
DAILY_DRAWDOWN_LIMIT_USDT=6

# Scaling levels (set to 0 to disable)
SCALE_LEVEL1_MARGIN_USDT=5
SCALE_LEVEL2_MARGIN_USDT=0
```

### Key Parameters (`config.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `main_interval` | `15m` | Signal timeframe |
| `context_interval` | `1h` | Trend-bias timeframe |
| `leverage` | `20` | Futures leverage |
| `fixed_margin_per_trade_usdt` | `5.0` | Margin per entry |
| `tp_rr` | `1.8` | Risk/reward ratio |
| `cooldown_sec` | `180` | Seconds between entries |
| `max_consecutive_losses` | `2` | Losses before pause |
| `daily_drawdown_limit_usdt` | `6.0` | Max daily loss (USD) |
| `risk_pause_after_losses_sec` | `3600` | Pause duration after loss limit |

---

## Run

```bash
python main.py
```

---

## Operational Flow

1. Load config and historical candles for all symbols.
2. Start WebSocket multiplexer in chunks of 50 streams.
3. On each M15 candle close:
   - Evaluate strategy across all symbols in parallel.
   - Broadcast all valid signals to Telegram.
   - Execute the highest-scored signal if `RiskManager` allows.
4. After execution:
   - Place TP/SL orders.
   - Start monitoring thread.
   - Apply exit / scale-in rules based on runtime state.

---

## Logs

- **Console:** heartbeat, warnings, errors.
- **File:** `logs/trades.log` — entry, exit, scale, and monitor events.

---

## Recommended Practices

- Always start with `BINANCE_TESTNET=true`.
- Validate with `USE_PAPER_TRADING=true` before live deployment.
- Never commit your `.env` file.
- Review `logs/trades.log` before tuning any parameter.
