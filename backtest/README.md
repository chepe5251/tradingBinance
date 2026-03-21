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
| `TOP_SYMBOLS` | `250` | Número máximo de pares a analizar (top N por volumen) |
| `INTERVALS` | `["15m", "1h", "4h"]` | Timeframes a evaluar |
| `CANDLES_PER_INTERVAL` | `15m: 1500, 1h: 720, 4h: 500` | Velas descargadas por símbolo/intervalo |
| `INITIAL_CAPITAL` | `500.0` | Capital inicial en USDT |
| `MARGIN_PER_TRADE` | `5.0` | Margen por trade en USDT |
| `LEVERAGE` | `20` | Apalancamiento simulado (igual que en producción) |
| `COMMISSION_PCT` | `0.0004` | Comisión por lado (taker 0.04%) |
| `MAX_CANDLES_HOLD` | `50` | Velas máximas antes de cerrar por timeout |
| `SKIP_AFTER_SIGNAL` | `10` | Velas a saltar después de cada señal |
| `MAX_DL_WORKERS` | `60` | Threads paralelos para descarga (Fase 1) |
| `SIM_WORKERS` | `cpu_count()` | Procesos paralelos para simulación (Fase 2) |

---

## Salida

### Consola

Progreso en tiempo real y reporte final de **12 secciones**:

1. Resumen general (trades, WR, PnL, avg win/loss, RR real, Profit Factor, WR breakeven)
2. Por timeframe + lado (15m BUY, 1h BUY, 4h BUY)
3. Por rango de score (0-1, 1-2, 2-3, 3-4, 4+)
4. Por duración en velas (0-5, 5-10, 10-20, 20-35, 35+)
5. Por fase de mercado (UPTREND, DOWNTREND, MIXED)
6. Por ratio de volumen (<1.5×, 1.5-2.0×, 2.0-3.0×, >3.0×)
7. Por RSI en señal (<48, 48-52, 52-56, 56-60, 60-64, 64-68, ≥68)
8. Top 5 mejores y peores pares por PnL
9. Trades descartados (4h SELL bloqueados, score < 1.0)
10. Equity curve y drawdown (max DD, Calmar ratio, rachas consecutivas)
11. Frecuencia de trades (trades/día por intervalo)
12. Rutas a los archivos CSV generados

### CSV de trades

Archivo guardado en `backtest/results/backtest_YYYYMMDD_HHMMSS.csv`:

| Columna | Descripción |
|---------|-------------|
| `symbol` | Par operado |
| `interval` | Timeframe |
| `side` | BUY |
| `entry_time` | Timestamp de entrada (cierre de vela de confirmación) |
| `exit_time` | Timestamp de salida |
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

Archivo guardado en `backtest/results/analysis_YYYYMMDD_HHMMSS.csv` con estadísticas agregadas (total_trades, wins, losses, timeouts, winrate, total_pnl, avg_pnl, avg_win, avg_loss, rr_real, profit_factor) por grupo: `interval`, `interval_side`, `score_range`, `candles_held`, `market_phase`, `vol_ratio`, `rsi_at_signal`, `ema_spread`, `body_ratio`, `hour_utc`, `weekday`.

### CSV de equity

Archivo guardado en `backtest/results/equity_YYYYMMDD_HHMMSS.csv` con curva de equity trade-por-trade: `trade_number`, `entry_time`, `symbol`, `interval`, `pnl_usdt`, `cumulative_pnl`, `peak`, `drawdown`.

---

## Notas

- La simulación es **candle-by-candle** — no hay lookahead bias.
- En caso de que SL y TP se toquen en la misma vela, se asume SL (worst case).
- Los trades con `TIMEOUT` se cierran al `close` de la vela 50.
- La descarga usa `ThreadPoolExecutor(60)` (Fase 1) y la simulación usa `ProcessPoolExecutor(cpu_count)` (Fase 2) para máxima velocidad.
- El rate limiter interno respeta el presupuesto de 2300 weight/min de Binance para evitar errores 429.
- Los 4h SELL están bloqueados (la estrategia es long-only).
- Se requieren al menos 230 velas por símbolo para que EMA200 sea significativo.
