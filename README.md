# Binance Futures Scalping Bot

> Algorithmic trading bot for **Binance USDT-M Perpetual Futures**.
> Scans all USDT-M perpetual pairs in real time, detects high-probability **EMA Pullback Long-Only** setups on M15/1H/4H, and executes one position at a time with automatic TP/SL protection, trailing stop, and loss-based scaling.

---

> **Risk Warning**
> This software places and cancels real orders on Binance Futures. Futures trading with leverage carries a high risk of loss, including total loss of deposited capital. Start with `BINANCE_TESTNET=true` and validate with `USE_PAPER_TRADING=true` before using real capital. Past performance of a strategy in testing is not indicative of future results.

---

## Table of Contents

- [Features](#features)
- [Strategy](#strategy)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Bot](#running-the-bot)
- [Trade Lifecycle](#trade-lifecycle)
- [Loss-Based Scaling](#loss-based-scaling)
- [Risk Management](#risk-management)
- [Telegram Alerts](#telegram-alerts)
- [Logs](#logs)
- [Project Structure](#project-structure)
- [Disclaimer](#disclaimer)

---

## Features

| Feature | Detail |
|---|---|
| Symbol universe | All USDT-M perpetual pairs loaded at startup |
| Signal timeframes | M15, 1H, 4H (long-only) |
| Entry | Limit order with automatic market fallback after 6 s |
| Protection | Mandatory TP + SL with auto-recovery if orders disappear |
| Breakeven | SL moved to entry once +0.5 % profit is reached |
| Trailing stop | ATR-based trail activates after breakeven |
| Scaling | Up to 5 scale-in levels on adverse moves |
| Risk controls | Cooldown, consecutive-loss pause, daily drawdown cap |
| Alerts | Telegram notifications for every signal and trade event |
| WebSocket | Chunked multiplexer with stale detection and auto-restart |
| Paper mode | Full simulation without touching the exchange |

---

## Strategy

### EMA Pullback Long-Only — M15 / 1H / 4H

Detects high-probability pullback entries by waiting for price to retrace to EMA20 within a well-aligned EMA20/50/200 uptrend, then requiring a bullish rejection candle followed by a break-of-high confirmation candle.

**Long-only.** Shorts were removed after backtesting showed 35.5% WR and negative net PnL across all timeframes.

---

#### Entry Logic — all 9 conditions must pass in order

| # | Condition | Detail |
|---|-----------|--------|
| 1 | **Structural uptrend** | `EMA20 > EMA50 > EMA200` |
| 2 | **Minimum EMA separation** | `EMA20 − EMA50 ≥ 0.15 × ATR` — filters flat/ranging markets |
| 3 | **Not overextended** | `EMA20 − EMA50 ≤ 1.0 × ATR` — pullbacks don't bounce when trend is stretched |
| 4 | **Price pulled back to EMA20** | Signal candle `low` within ±0.8 ATR of EMA20 |
| 5 | **Structure intact** | Signal candle `close > EMA50` |
| 6 | **RSI healthy pullback zone** | `48 ≤ RSI ≤ 68` — not weak, not overbought |
| 7 | **Bullish rejection candle** | `body_ratio ≥ 0.35`, `close > open`, close in upper third of range |
| 8 | **Volume in optimal range** | `1.05× ≤ vol ≤ 1.5× avg` — confirms interest, excludes exhaustion spikes |
| 9 | **Confirmation candle** | Next candle closes above signal candle high |

#### Levels

```
Entry  = close of confirmation candle
SL     = signal candle low − 0.1 × ATR
TP     = entry + (risk × 2.0)   ← RR 2:1
```

#### Signal Score (max ~4.0)

| Component | Formula | Max |
|-----------|---------|-----|
| Body quality | `((body_ratio − 0.35) / 0.65) × 2` | 2.0 |
| RSI sweet spot | `+1.0` if RSI in 53–63, else 0 | 1.0 |
| EMA spread strength | `(spread_atr − 0.15) × 2`, capped at 1.0 | 1.0 |

Minimum score to fire a signal: **1.5**

---

### Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `EMA_FAST` | 20 | Fast EMA for pullback zone |
| `EMA_MID` | 50 | Mid EMA for structure |
| `EMA_SLOW` | 200 | Trend filter |
| `PULLBACK_TOLERANCE_ATR` | 0.8 | Tolerance band around EMA20 for pullback detection |
| `MIN_EMA_SPREAD_ATR` | 0.15 | Minimum EMA20−EMA50 spread (filters ranging) |
| `MAX_EMA_SPREAD_ATR` | 1.0 | Maximum spread (filters overextended trends) |
| `MIN_BODY_RATIO` | 0.35 | Minimum rejection candle body quality |
| `MIN_VOL_MULT` | 1.05 | Minimum volume vs 20-bar average |
| `MAX_VOL_MULT` | 1.5 | Maximum volume (excludes exhaustion spikes) |
| `RSI_LONG_MIN` | 48.0 | Lower RSI bound |
| `RSI_LONG_MAX` | 68.0 | Upper RSI bound |
| `RR_TARGET` | 2.0 | Risk:Reward ratio |
| `MIN_SCORE` | 1.5 | Minimum score to emit a signal |

---

## Architecture

```
tradingPython/
├── main.py          # Orchestrator: stream, signals, execution, monitoring
├── strategy.py      # Signal engine: 7-filter sweep detector + scorer
├── execution.py     # Order router: limit/market, TP/SL, OCO monitor, trailing
├── data_stream.py   # WebSocket multiplexer + in-memory candle cache
├── risk.py          # Cooldown, loss pause, daily drawdown guard
├── config.py        # Settings dataclass + .env loader
├── indicators.py    # Shared indicator helpers (EMA, ATR)
├── test_trade.py    # Manual script to validate minimal order placement
├── .env.example     # Configuration template (copy to .env)
└── requirements.txt # Pinned Python dependencies
```

### Component Diagram

```
          .env
            │
            ▼
        config.py  ──► Settings
            │
       ┌────┴──────────────────────────────────┐
       │                                       │
       ▼                                       ▼
  data_stream.py                         risk.py
  (WebSocket + cache)                (RiskManager)
       │                                       │
       │  candle close                         │ can_trade?
       ▼                                       │
  strategy.py ──► signal dict ────────────────►│
  (evaluate_signal)                            │
                                               ▼
                                          main.py
                                     (on_main_close)
                                               │
                                               ▼
                                        execution.py
                                     (FuturesExecutor)
                                    limit → TP/SL → trail
                                               │
                                               ▼
                                       Binance API
```

---

## Requirements

- Python 3.10+
- Binance Futures account (testnet or live)

---

## Installation

> For detailed per-OS instructions (Windows, macOS, Linux, systemd service, tmux, Task Scheduler) see [INSTALL.md](INSTALL.md).

```bash
# 1. Clone the repository
git clone https://github.com/chepe5251/tradingBinance.git
cd tradingBinance

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install pinned dependencies
pip install -r requirements.txt

# 4. Copy the configuration template
cp .env.example .env   # then edit .env with your credentials
```

---

## Configuration

Edit `.env` with your credentials and preferred parameters:

```env
# Binance API credentials
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# Start in testnet — change to false only when ready for live trading
BINANCE_TESTNET=true
BINANCE_DATA_TESTNET=false

# Telegram alerts (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Simulate trades without touching the exchange
USE_PAPER_TRADING=true
PAPER_START_BALANCE=25

# Capital controls
FIXED_MARGIN_PER_TRADE_USDT=5
DAILY_DRAWDOWN_LIMIT_USDT=6

# Scaling levels (set to 0 to disable)
SCALE_LEVEL1_MARGIN_USDT=5
SCALE_LEVEL2_MARGIN_USDT=0
```

See [`.env.example`](.env.example) for the full list of available options.

### Key Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `BINANCE_TESTNET` | `true` | Route execution to testnet |
| `FIXED_MARGIN_PER_TRADE_USDT` | `5.0` | USDT margin per trade entry |
| `DAILY_DRAWDOWN_LIMIT_USDT` | `6.0` | Bot pauses when daily loss exceeds this |
| `MARGIN_UTILIZATION` | `0.95` | Fraction of balance available as margin |
| `SCALE_LEVEL1_MARGIN_USDT` | `5.0` | Extra margin added at first scale level |
| `USE_PAPER_TRADING` | `false` | Full simulation mode |
| `SYMBOLS` | *(all)* | Comma-separated symbol filter (empty = all USDT-M perpetuals) |

All defaults are defined in [`config.py`](config.py). Settings are validated and bounded at startup.

---

## Running the Bot

```bash
python main.py
```

The bot will:

1. Load all USDT-M perpetual symbols from the exchange.
2. Bootstrap historical candles (600 × M15, 400 × 1H per symbol).
3. Open WebSocket streams in chunks of 50.
4. Begin evaluating signals on every M15 candle close.

To stop the bot, press `Ctrl+C`. Open TP/SL orders remain active on the exchange and must be cancelled manually if desired.

---

## Trade Lifecycle

```
M15 / 1H / 4H candle closes
        │
        ▼
evaluate_signal() ── all 9 conditions pass? ──► signal candidate
        │
        ▼
  score ≥ 1.5? AND side == BUY?
        │                       │
        │ NO                    │ YES
        ▼                       ▼
  return None             signal accepted
                                │
                                ▼ (signals sorted by score)
RiskManager.can_trade()  AND  no open position?
        │
        ├─ NO  ──► broadcast signal to Telegram, skip execution
        │
        └─ YES ──► place_limit_with_market_fallback()
                        │
                        ├─ Limit fills within 6 s  ──► "MAKER"
                        └─ Timeout ──► cancel + market remaining ──► "TAKER"
                                │
                                ▼
                        place_tp_sl()  (TAKE_PROFIT + STOP, reduceOnly)
                                │
                                ▼
                        protect_and_monitor() thread
                        ┌───────────────────────────┐
                        │  every 0.5 s:             │
                        │  • check TP / SL status   │
                        │  • recover missing orders │
                        │  • breakeven @ +0.5 %     │
                        │  • trail after breakeven  │
                        │  • scale-in on drawdown   │
                        │  • early exit on EMA cross│
                        └───────────────────────────┘
                                │
                        TP / SL / EARLY exit
                                │
                        RiskManager.update_trade(pnl)
```

---

## Loss-Based Scaling

When a position moves against the entry, the bot can add margin at predefined drawdown thresholds to lower the average entry price.

| Level | Floating Loss Trigger | Additional Margin | Cumulative Exposure |
|-------|-----------------------|------------------|---------------------|
| Entry | — | $5 | $5 |
| L1 | −50 % of $5 = $2.50 | $5 | $10 |
| L2 | −100 % of $5 = $5.00 | $10 | $20 |
| L3 | −200 % of $5 = $10.00 | $20 | $40 |
| L4 | −400 % of $5 = $20.00 | $40 | $80 |
| L5 | −800 % of $5 = $40.00 | $80 | $160 |

> Set `SCALE_LEVEL*_MARGIN_USDT=0` to disable any individual level.
> Be aware that scaling significantly increases total risk exposure.

---

## Risk Management

The `RiskManager` enforces three independent guards:

| Guard | Default | Behaviour |
|-------|---------|-----------|
| **Cooldown** | 180 s | Minimum gap between entry signals |
| **Consecutive losses** | 2 | After 2 losses in a row, pause trading for 1 hour |
| **Daily drawdown** | $6 USDT | Bot pauses for the rest of the UTC day |

All counters reset at UTC midnight.

---

## Telegram Alerts

When `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set, the bot sends:

- **Signal alert** — for every valid setup detected across all USDT-M pairs, including entry, SL, TP, R:R, score, and EMA/RSI details.
- **Trade opened** — confirmation with fill price and execution type (MAKER / TAKER).
- **Breakeven activated** — when SL is moved to entry.
- **Trailing stop updated** — each time the trail advances.
- **Scale-in added** — when a new position layer is added.
- **Trade closed** — result (TP / SL / EARLY) with PnL.

Rate limiting is handled automatically (HTTP 429 retry with back-off).

---

## Logs

| Destination | Content |
|-------------|---------|
| Console (`INFO`) | Heartbeat, stream events, warnings, errors |
| `logs/trades.log` | Every signal, skip reason, entry, exit, scale, and monitor event |

```bash
# tail live trades log
tail -f logs/trades.log
```

---

## Project Structure

```
main.py          Application entry point and orchestration loop
strategy.py      EMA Pullback Long-Only signal engine (backtest-optimized)
execution.py     Order routing, rounding, OCO monitor, trailing stop
data_stream.py   WebSocket kline multiplexer with auto-restart
risk.py          RiskManager: cooldown, loss pause, drawdown guard
config.py        Settings dataclass and .env loader
indicators.py    Shared EMA / ATR helpers
test_trade.py    Manual order validation script
backtest/        Candle-by-candle backtester across all USDT-M pairs
```

---

## Disclaimer

This project is provided for **educational and research purposes only**.
The authors are not responsible for financial losses resulting from its use.
Always perform your own due diligence before deploying any automated trading system with real capital.
Cryptocurrency futures trading is highly speculative and not suitable for all investors.
