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

## Strategy: M15 Pullback Continuation with 1H Confirmation

### Overview

The strategy looks for **clean pullbacks inside an established trend**, entering
on the first candle that breaks the pullback structure. Entries in
over-extended or choppy conditions are rejected by multiple filters.

### Signal Generation — LONG

All conditions must be met in order. First failure = no signal.

| # | Rule | Condition |
|---|------|-----------|
| 1 | **1H bias bullish** | Last 1H close `> EMA50` AND `EMA50 rising` (current > previous) |
| 2 | **M15 trend aligned** | `EMA7 > EMA25` AND `DIF > 0` |
| 3 | **Anti-range filter** | EMA7/EMA25 crossed `< 3` times in the last 15 candles |
| 4 | **Pullback structure** | Candle −1 is red with `body/range ≤ 0.6`; low `≥ EMA25`; not 3 consecutive red candles |
| 5 | **2-candle pullback** | If candles −1 and −2 are both red, candle −2 must also have `body/range ≤ 0.6` |
| 6 | **Entry trigger** | Current high `> prev1 high` AND current close `> prev1 close` |
| 7 | **MACD momentum** | Current MACD histogram `> previous bar` (expanding upward) |
| 8 | **Volume confirmation** | Current volume `≥ 1.3 × avg(last 5 candles)` |
| 9 | **Anti-late-entry** | Current range `< 1.6 × ATR`; distance from EMA7 `≤ 0.3 × ATR`; `body/range ≤ 0.85` |
| 10 | **Impulse quality** | Pullback body `≤ 60%` of the 8-candle swing range |
| 11 | **Risk validity** | `risk_per_unit ≥ 0.5 × ATR` |

- **Stop loss:** swing low of last 8 candles
- **Take profit:** `entry + risk × 1.8`

### Signal Generation — SHORT

Exact mirror of LONG logic:
- 1H close `< EMA50`, `EMA50 falling`
- `EMA7 < EMA25`, `DIF < 0`
- Pullback: 1–2 green candles, `body/range ≤ 0.6`, high `≤ EMA25`
- Entry trigger: current low `< prev1 low` AND close `< prev1 close`
- MACD histogram `< previous bar` (expanding downward)
- **Stop loss:** swing high of last 8 candles

### Score System (minimum 3.0 to emit signal)

| Component | Formula | Max |
|-----------|---------|-----|
| 1H trend strength | `abs(EMA50_now − EMA50_prev) / EMA50_prev × 2500` | 3.0 |
| Pullback quality | `(0.65 − pb_body_ratio) × 6` | 2.0 |
| Risk vs ATR | `risk_per_unit / ATR` | 2.0 |
| Volume strength | `(vol_current / vol_avg5) − 1.0` | 1.5 |
| Late-entry penalty | `−((candle_range / ATR) − 1.0)` | −2.0 |
| Volatility penalty | `−((ATR / ATR_avg20 − 1.3) × 3)` | −1.5 |

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
