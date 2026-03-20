# Backtest — EMA Pullback Long-Only

Script independiente que descarga datos históricos de Binance Futures, corre la estrategia `evaluate_signal` candle-by-candle en M15 / 1H / 4H para **todos los pares USDT-M perpetuos** por volumen, y genera un reporte completo en consola más dos archivos CSV.

---

## Requisitos

Las mismas dependencias que el bot principal (`python-binance`, `pandas`). Instalarlas desde la raíz del repositorio:

```bash
pip install -r requirements.txt
```

---

## Configuración

El script lee automáticamente el archivo `.env` de la raíz del repositorio. No se necesita ningún archivo adicional.

Variables utilizadas:

| Variable | Descripción |
|----------|-------------|
| `BINANCE_API_KEY` | API key de Binance (opcional — los datos históricos son públicos) |
| `BINANCE_API_SECRET` | API secret de Binance (opcional) |

Si las claves de Binance están vacías, el cliente se conecta sin autenticación (suficiente para descargar klines públicos).

---

## Ejecución

Desde la **raíz del repositorio**:

```bash
python backtest/backtest.py
```

---

## Parámetros configurables

Al inicio de `backtest.py`:

| Constante | Default | Descripción |
|-----------|---------|-------------|
| `BACKTEST_DAYS` | `30` | Período de referencia en días |
| `TOP_SYMBOLS` | `999` | Número máximo de pares a analizar (999 = todos) |
| `INTERVALS` | `["15m", "1h", "4h"]` | Timeframes a evaluar |
| `CANDLES_PER_INTERVAL` | `15m: 1500, 1h: 720, 4h: 500` | Velas descargadas por símbolo/intervalo |
| `INITIAL_CAPITAL` | `500.0` | Capital inicial en USDT |
| `MARGIN_PER_TRADE` | `5.0` | Margen por trade en USDT |
| `LEVERAGE` | `10` | Apalancamiento simulado |
| `COMMISSION_PCT` | `0.0004` | Comisión por lado (taker 0.04%) |
| `MAX_CANDLES_HOLD` | `50` | Velas máximas antes de cerrar por timeout |
| `SKIP_AFTER_SIGNAL` | `10` | Velas a saltar después de cada señal |

---

## Salida

### Consola

Progreso en tiempo real y reporte final de **10 secciones**:

1. Resumen general (trades, WR, PnL, ROI)
2. Por timeframe + lado (15m BUY, 1h BUY, 4h BUY)
3. Por rango de score (≤2.0, 2.0–3.0, >3.0)
4. Por duración en velas (1–5, 6–15, 16–50, timeout)
5. Por fase de mercado
6. Por ratio de volumen
7. Por RSI en señal
8. Top 5 mejores y peores pares
9. Trades descartados (4h SELL bloqueados, score < 1.0)
10. Rutas a los archivos CSV generados

### CSV de trades

Archivo guardado en `backtest/results/backtest_YYYYMMDD_HHMMSS.csv`:

| Columna | Descripción |
|---------|-------------|
| `symbol` | Par operado |
| `interval` | Timeframe |
| `side` | BUY |
| `entry_price` | Precio de entrada |
| `exit_price` | Precio de salida |
| `stop_price` | Stop loss de la señal |
| `tp_price` | Take profit de la señal |
| `pnl_usdt` | PnL neto en USDT (incluye comisiones) |
| `result` | WIN / LOSS / TIMEOUT |
| `candles_held` | Velas que duró el trade |
| `score` | Score de la señal (0–4) |
| `ema_spread` | EMA20−EMA50 en la señal (precio) |
| `rsi_at_signal` | RSI en la vela señal |
| `vol_ratio` | Volumen / avg_vol en la señal |
| `body_ratio` | Ratio cuerpo/rango de la vela señal |
| `distance_to_tp` | Distancia entry→TP en USDT |
| `distance_to_sl` | Distancia entry→SL en USDT |
| `rr_planned` | R:R planificado |
| `market_phase` | Fase de mercado estimada |

### CSV de análisis

Archivo guardado en `backtest/results/analysis_YYYYMMDD_HHMMSS.csv` con estadísticas agregadas por grupo (interval_side, score_range, candles_held, market_phase, vol_ratio, rsi_at_signal).

---

## Notas

- La simulación es **candle-by-candle** — no hay lookahead bias.
- En caso de que SL y TP se toquen en la misma vela, se asume SL (worst case).
- Los trades con `TIMEOUT` se cierran al `close` de la vela 50.
- Los reintentos de descarga incluyen backoff de 5s / 10s / 15s para manejar errores de red.
- Los 4h SELL están bloqueados (la estrategia es long-only).
- Se requieren al menos 230 velas por símbolo para que EMA200 sea significativo.
