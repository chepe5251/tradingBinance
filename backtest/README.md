# Backtest — Order Block + Break of Structure

Script independiente que descarga datos históricos de Binance Futures, corre la estrategia `evaluate_signal` candle-by-candle en M15 / 1H / 4H para los top 50 pares USDT-M por volumen, y envía un reporte de métricas por Telegram.

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
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram para el reporte |
| `TELEGRAM_CHAT_ID` | Chat ID donde se manda el reporte |

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
| `BACKTEST_DAYS` | `30` | Período histórico en días |
| `TOP_SYMBOLS` | `50` | Número de pares a analizar |
| `INTERVALS` | `["15m", "1h", "4h"]` | Timeframes a evaluar |
| `INITIAL_CAPITAL` | `100.0` | Capital inicial en USDT |
| `MARGIN_PER_TRADE` | `5.0` | Margen por trade en USDT |
| `LEVERAGE` | `10` | Apalancamiento simulado |
| `COMMISSION_PCT` | `0.0004` | Comisión por lado (taker 0.04%) |
| `MAX_CANDLES_HOLD` | `50` | Velas máximas antes de cerrar por timeout |
| `SKIP_AFTER_SIGNAL` | `10` | Velas a saltar después de cada señal |

---

## Salida

### Consola
Progreso en tiempo real y el reporte final completo.

### Telegram
Reporte formateado con métricas por timeframe, PnL total, mejor/peor par y ROI.

### CSV
Archivo guardado automáticamente en `backtest/results/backtest_YYYYMMDD_HHMMSS.csv` con todas las operaciones simuladas:

| Columna | Descripción |
|---------|-------------|
| `symbol` | Par operado |
| `interval` | Timeframe |
| `side` | BUY / SELL |
| `entry_price` | Precio de entrada |
| `exit_price` | Precio de salida |
| `stop_price` | Stop loss de la señal |
| `tp_price` | Take profit de la señal |
| `pnl_usdt` | PnL neto en USDT (incluye comisiones) |
| `result` | WIN / LOSS / TIMEOUT |
| `candles_held` | Velas que duró el trade |
| `score` | Score de la señal (0–6) |

---

## Notas

- La simulación es **candle-by-candle** — no hay lookahead bias.
- En caso de que SL y TP se toquen en la misma vela, se asume SL (worst case).
- Los trades con `TIMEOUT` se cierran al `close` de la vela 50.
- El backtest **no** aplica los filtros de `_layered_signal_check` de `main.py` — evalúa las señales puras de `strategy.py`.
