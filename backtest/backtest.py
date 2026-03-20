"""Backtest — Order Block + Break of Structure strategy.

Downloads historical Binance Futures klines, runs evaluate_signal candle-by-candle
for M15 / 1H / 4H across the top 50 USDT-M pairs, calculates metrics, and sends
a Telegram report.

Usage (from repo root):
    python backtest/backtest.py
"""
from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
from binance import Client

# ── strategy import (one level up) ───────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategy import evaluate_signal  # noqa: E402

# ── configuration ─────────────────────────────────────────────────────────────
BACKTEST_DAYS = 30
TOP_SYMBOLS = 50
INTERVALS = ["15m", "1h", "4h"]
CANDLES_PER_INTERVAL: dict[str, int] = {"15m": 1500, "1h": 720, "4h": 500}
INITIAL_CAPITAL = 100.0
MARGIN_PER_TRADE = 5.0
LEVERAGE = 10
COMMISSION_PCT = 0.0004   # 0.04 % per side (taker)
ATR_PERIOD = 14

# evaluate_signal parameters — same defaults as main.py
_EVAL_KWARGS: dict = dict(
    ema_trend=200,
    ema_fast=20,
    ema_mid=50,
    atr_period=ATR_PERIOD,
    atr_avg_window=20,
    volume_avg_window=20,
    rsi_period=14,
    rsi_long_min=40.0,
    rsi_long_max=70.0,
    rsi_short_min=30.0,
    rsi_short_max=60.0,
    volume_min_ratio=1.0,
)

MAX_CANDLES_HOLD = 50   # close at market after this many candles
SKIP_AFTER_SIGNAL = 10  # skip candles after a signal to avoid overlap


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_env() -> dict[str, str]:
    """Load key=value pairs from ../.env relative to this script."""
    env: dict[str, str] = {}
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    env_path = os.path.normpath(env_path)
    if not os.path.exists(env_path):
        return env
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def _send_telegram(token: str, chat_id: str, message: str) -> None:
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urlencode({"chat_id": chat_id, "text": message})
    for attempt in range(1, 4):
        try:
            req = Request(
                url,
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urlopen(req, timeout=15):
                return
        except HTTPError as exc:
            if exc.code == 429:
                time.sleep(5)
            elif attempt < 3:
                time.sleep(attempt * 2.0)
        except Exception:
            if attempt < 3:
                time.sleep(attempt * 2.0)


def _load_symbols(client: Client) -> list[str]:
    """Return top TOP_SYMBOLS USDT-M perpetual symbols by 24h quote volume."""
    try:
        info = client.futures_exchange_info()
    except Exception as exc:
        print(f"[ERROR] futures_exchange_info: {exc}")
        return []

    perp: set[str] = set()
    for s in info.get("symbols", []):
        if (
            s.get("status") == "TRADING"
            and s.get("contractType") == "PERPETUAL"
            and s.get("quoteAsset") == "USDT"
            and str(s.get("symbol", "")).endswith("USDT")
        ):
            perp.add(s["symbol"])

    try:
        tickers = client.futures_ticker()
    except Exception as exc:
        print(f"[ERROR] futures_ticker: {exc}")
        return sorted(perp)[:TOP_SYMBOLS]

    vol_map: dict[str, float] = {}
    for t in tickers:
        sym = t.get("symbol", "")
        if sym in perp:
            try:
                vol_map[sym] = float(t.get("quoteVolume", 0) or 0)
            except Exception:
                vol_map[sym] = 0.0

    ranked = sorted(perp, key=lambda s: vol_map.get(s, 0.0), reverse=True)
    return ranked[:TOP_SYMBOLS]


def _fetch_klines(client: Client, symbol: str, interval: str, limit: int) -> pd.DataFrame:
    """Download klines and return a clean DataFrame."""
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    rows = [
        {
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": int(k[6]),
        }
        for k in klines
    ]
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df


def _simulate_trades(df: pd.DataFrame, symbol: str, interval: str) -> list[dict]:
    """Walk through df candle-by-candle and simulate every signal."""
    trades: list[dict] = []
    i = 230  # minimum candles needed for EMA200
    n = len(df)

    while i < n - 1:
        sub = df.iloc[: i + 1]
        try:
            signal = evaluate_signal(sub, pd.DataFrame(), **_EVAL_KWARGS)
        except Exception:
            i += 1
            continue

        if signal is None:
            i += 1
            continue

        entry_price = float(signal["price"])
        stop_price = float(signal["stop_price"])
        tp_price = float(signal["tp_price"])
        side = signal["side"]
        score = float(signal.get("score") or 0.0)

        if entry_price <= 0 or stop_price <= 0 or tp_price <= 0:
            i += 1
            continue

        qty = (MARGIN_PER_TRADE * LEVERAGE) / entry_price
        commission = qty * entry_price * COMMISSION_PCT * 2

        # Simulate: scan next candles for SL/TP hit
        result = "TIMEOUT"
        exit_price = float(df.iloc[min(i + MAX_CANDLES_HOLD, n - 1)]["close"])
        candles_held = 0

        for j in range(i + 1, min(i + MAX_CANDLES_HOLD + 1, n)):
            candle = df.iloc[j]
            candles_held = j - i
            c_high = float(candle["high"])
            c_low = float(candle["low"])

            if side == "BUY":
                if c_high >= tp_price and c_low <= stop_price:
                    # Both hit same candle — assume worst case: SL hit first
                    result = "LOSS"
                    exit_price = stop_price
                    break
                if c_high >= tp_price:
                    result = "WIN"
                    exit_price = tp_price
                    break
                if c_low <= stop_price:
                    result = "LOSS"
                    exit_price = stop_price
                    break
            else:  # SELL
                if c_low <= tp_price and c_high >= stop_price:
                    result = "LOSS"
                    exit_price = stop_price
                    break
                if c_low <= tp_price:
                    result = "WIN"
                    exit_price = tp_price
                    break
                if c_high >= stop_price:
                    result = "LOSS"
                    exit_price = stop_price
                    break

        if side == "BUY":
            gross_pnl = (exit_price - entry_price) * qty
        else:
            gross_pnl = (entry_price - exit_price) * qty
        pnl_usdt = gross_pnl - commission

        trades.append({
            "symbol": symbol,
            "interval": interval,
            "side": side,
            "entry_price": round(entry_price, 8),
            "exit_price": round(exit_price, 8),
            "stop_price": round(stop_price, 8),
            "tp_price": round(tp_price, 8),
            "pnl_usdt": round(pnl_usdt, 4),
            "result": result,
            "candles_held": candles_held,
            "score": score,
            "signal_candle": i,
        })

        i += SKIP_AFTER_SIGNAL

    return trades


def _max_consecutive_losses(trades: list[dict]) -> int:
    max_streak = cur = 0
    for t in trades:
        if t["result"] == "LOSS":
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0
    return max_streak


def _build_report(
    all_trades: list[dict],
    date_from: datetime,
    date_to: datetime,
    n_symbols: int,
) -> str:
    sep = "━━━━━━━━━━━━━━━━━━"
    lines: list[str] = [
        f"📊 BACKTEST REPORT — {BACKTEST_DAYS} días",
        f"Período: {date_from.strftime('%Y-%m-%d')} a {date_to.strftime('%Y-%m-%d')}",
        f"Símbolos analizados: {n_symbols}",
        sep,
    ]

    total_pnl = 0.0
    total_wins = total_losses = total_timeouts = total_count = 0

    for iv in INTERVALS:
        iv_trades = [t for t in all_trades if t["interval"] == iv]
        if not iv_trades:
            lines.append(f"⏱ {iv.upper()}: 0 trades")
            continue
        wins = sum(1 for t in iv_trades if t["result"] == "WIN")
        losses = sum(1 for t in iv_trades if t["result"] == "LOSS")
        timeouts = sum(1 for t in iv_trades if t["result"] == "TIMEOUT")
        cnt = len(iv_trades)
        wr = wins / cnt * 100 if cnt else 0.0
        pnl = sum(t["pnl_usdt"] for t in iv_trades)
        sign = "+" if pnl >= 0 else ""
        lines.append(
            f"⏱ {iv.upper()}: {cnt} trades | WR: {wr:.1f}% | PnL: {sign}${pnl:.2f}"
        )
        total_pnl += pnl
        total_wins += wins
        total_losses += losses
        total_timeouts += timeouts
        total_count += cnt

    lines.append(sep)

    sign = "+" if total_pnl >= 0 else ""
    lines += [
        f"✅ Total trades: {total_count}",
        f"✅ Ganados: {total_wins} | Perdidos: {total_losses} | Timeout: {total_timeouts}",
        f"✅ PnL Total: {sign}${total_pnl:.2f}",
    ]

    # Best / worst symbol
    sym_pnl: dict[str, float] = {}
    for t in all_trades:
        sym_pnl[t["symbol"]] = sym_pnl.get(t["symbol"], 0.0) + t["pnl_usdt"]

    if sym_pnl:
        best_sym = max(sym_pnl, key=sym_pnl.get)  # type: ignore[arg-type]
        worst_sym = min(sym_pnl, key=sym_pnl.get)  # type: ignore[arg-type]
        best_sign = "+" if sym_pnl[best_sym] >= 0 else ""
        worst_sign = "+" if sym_pnl[worst_sym] >= 0 else ""
        lines.append(f"📈 Mejor par: {best_sym} ({best_sign}${sym_pnl[best_sym]:.2f})")
        lines.append(f"📉 Peor par: {worst_sym} ({worst_sign}${sym_pnl[worst_sym]:.2f})")

    max_losses = _max_consecutive_losses(all_trades)
    lines.append(f"🔴 Racha pérdidas: {max_losses} consecutivas")
    lines.append(sep)

    capital_final = INITIAL_CAPITAL + total_pnl
    roi = (total_pnl / INITIAL_CAPITAL) * 100
    roi_sign = "+" if roi >= 0 else ""
    lines += [
        f"Capital inicial: ${INITIAL_CAPITAL:.0f}",
        f"Capital final: ${capital_final:.2f}",
        f"ROI: {roi_sign}{roi:.2f}%",
    ]

    if total_pnl > 0:
        lines.append("✅ ESTRATEGIA RENTABLE")
    else:
        lines.append("❌ ESTRATEGIA NO RENTABLE — revisar parámetros")

    return "\n".join(lines)


def _save_csv(all_trades: list[dict]) -> str:
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(results_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(results_dir, f"backtest_{ts}.csv")
    if not all_trades:
        return path
    fieldnames = list(all_trades[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_trades)
    return path


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    env = _load_env()
    api_key = env.get("BINANCE_API_KEY", "")
    api_secret = env.get("BINANCE_API_SECRET", "")
    tg_token = env.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = env.get("TELEGRAM_CHAT_ID", "")

    client = Client(api_key, api_secret)

    print("Cargando símbolos...")
    symbols = _load_symbols(client)
    if not symbols:
        print("[ERROR] No se pudieron cargar los símbolos.")
        return
    print(f"Símbolos seleccionados: {len(symbols)}")

    date_to = datetime.now(timezone.utc)

    all_trades: list[dict] = []
    total_tasks = len(symbols) * len(INTERVALS)
    task_num = 0

    for sym in symbols:
        for interval in INTERVALS:
            task_num += 1
            limit = CANDLES_PER_INTERVAL[interval]
            print(f"Analizando {sym} {interval}... ({task_num}/{total_tasks})")

            try:
                df = _fetch_klines(client, sym, interval, limit)
            except Exception as exc:
                print(f"  [SKIP] {sym} {interval}: {exc}")
                continue

            if len(df) < 232:
                print(f"  [SKIP] {sym} {interval}: datos insuficientes ({len(df)} velas)")
                continue

            trades = _simulate_trades(df, sym, interval)
            all_trades.extend(trades)
            print(f"  → {len(trades)} señales")

    date_from = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    date_from_ts = date_to.timestamp() - (BACKTEST_DAYS * 86400)
    date_from = datetime.fromtimestamp(date_from_ts, tz=timezone.utc)

    report = _build_report(all_trades, date_from, date_to, len(symbols))

    print("\n" + "=" * 50)
    print(report)
    print("=" * 50 + "\n")

    if tg_token and tg_chat:
        print("Enviando reporte por Telegram...")
        try:
            _send_telegram(tg_token, tg_chat, report)
            print("Reporte enviado.")
        except Exception as exc:
            print(f"[WARN] Telegram falló: {exc}")
    else:
        print("[INFO] TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados — solo consola.")

    csv_path = _save_csv(all_trades)
    print(f"Resultados guardados en: {csv_path}")


if __name__ == "__main__":
    main()
