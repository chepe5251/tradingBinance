# Binance Futures Scalping Bot (USDT‑M)

## Objetivo
Bot de scalping 24/7 para **los 5 pares USDT‑M con mayor volumen** (por defecto) con entradas rápidas buscando **0.3%–0.5%** por trade, usando **LIMIT orders** y operando **una sola posición a la vez**.

## Estrategia (intravela)
- **EMA 200** (sesgo):
  - LONG solo si precio actual > EMA200
  - SHORT solo si precio actual < EMA200
- **EMA 9 / EMA 21** (entrada 1m):
  - LONG si EMA9 > EMA21
  - SHORT si EMA9 < EMA21
- **VWAP** (1m):
  - LONG solo si precio > VWAP
  - SHORT solo si precio < VWAP
- **RSI 14** (1m):
  - LONG si RSI > 50
  - SHORT si RSI < 50
- **Volumen**:
  - Opcional (por defecto desactivado)

## Reglas
- **Solo LIMIT orders**.
- **TP fijo** (0.3%–0.5%) y **SL fijo** (0.25%–0.35%).
- **Cooldown** 1–3 min entre trades.
- **Máximo 1 posición abierta**.
- **Pausa** tras 3 pérdidas consecutivas.
- **Stop diario** si drawdown > 5%.
- **Pausa por volatilidad** (rango de vela > umbral).

## Estructura
- `data_stream.py` → WebSocket (klines 1m) multi‑símbolo
- `indicators.py` → EMA/RSI/VWAP
- `strategy.py` → Señales
- `execution.py` → Órdenes limit + TP/SL
- `risk.py` → Gestión de riesgo
- `config.py` → Configuración
- `main.py` → Orquestación

## Instalación
```bash
pip install -r requirements.txt
```

## Configuración
Crea `.env` (usa `.env.example`):
```
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET=true
```

En `config.py` puedes ajustar:
- `leverage` (x5/x10)
- `tp_pct`, `sl_pct`
- `cooldown_sec`
- `max_consecutive_losses`
- `daily_drawdown_limit`
- `use_top_volume_symbols` y `top_volume_symbols_count`
- `symbols` (lista manual si no quieres top‑volumen)
- `extra_symbols` (siempre incluir, por defecto `BNBUSDT`)

## Ejecución
```bash
python main.py
```

## Pseudocódigo
```
load_settings()
load_initial_candles(1m, 5m)
start_websocket(1m, 5m)

on_new_1m_candle_close:
    if volatility_high: return
    if open_position: manage_or_skip
    if cooldown/limits breached: return

    signal = evaluate_signal(1m, 5m)
    if no signal: return

    entry_price = limit_with_retrace(signal)
    qty = calc_qty(capital, entry_price)
    place_limit_order(entry)

    if filled:
        place_tp_sl_orders()
        monitor_oco()
        update_risk()
```

