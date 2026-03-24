# Backtest & Analysis (Stage 2)

`backtest/backtest.py` downloads Binance Futures klines, simulates trades candle-by-candle, and writes three CSV files per run:

| File | Contents |
|---|---|
| `backtest_YYYYMMDD_HHMMSS.csv` | One row per simulated trade with full metadata |
| `analysis_YYYYMMDD_HHMMSS.csv` | Metrics grouped by interval, score, phase, vol, RSI, etc. |
| `equity_YYYYMMDD_HHMMSS.csv` | Equity curve with cumulative PnL and drawdown per trade |

**IMPORTANT — Stage 2 does NOT change live bot behaviour.**
All scripts in this directory are pure analysis tools. They do not modify leverage,
sizing, exposure, or any production parameter.

---

## Standard backtest

```bash
python backtest/backtest.py
```

Reads `.env` for API keys and strategy parameters.

### Console output sections

| Section | What it shows |
|---|---|
| 1. Resumen general | Total trades, WR, PF, expectancy, median PnL, best/worst trade |
| 2. Por timeframe y side | Performance per interval × direction |
| 3. Por score | Performance per signal score band |
| 4. Por duración | Performance by candles held |
| 5. Por market phase | UPTREND / DOWNTREND / MIXED EMA alignment |
| 6. Por volumen | Performance by vol_ratio at signal |
| 7. Por RSI | Performance by RSI band at signal |
| 8. Top 5 mejores/peores pares | Best and worst symbols |
| 9. Trades descartados | 4H SELL filter + score < 1.0 filter |
| 10. Equity curve y drawdown | Max DD, Calmar, consecutive streaks |
| 11. Frecuencia de trades | Trades/day, active days |
| 12. Concentración de top winners | What % of PnL comes from top 1/5/10/20 trades |
| 13. Archivos generados | Output CSV paths |

---

## Walk-forward analysis

Tests temporal consistency — does performance hold across different time periods?

```bash
# Default: 30-day windows, 15-day step
python backtest/walk_forward.py --csv backtest/results/backtest_YYYYMMDD_HHMMSS.csv

# Custom windows
python backtest/walk_forward.py \
    --csv backtest/results/backtest_YYYYMMDD_HHMMSS.csv \
    --window 45 --step 15
```

**Output:** `backtest/results/walk_forward_YYYYMMDD_HHMMSS.csv` — one row per window.

**How to interpret:**
- A strategy with stable edge shows consistent WR and PF across all windows.
- If ≥75% of windows have PF > 1.0 → verdict: CONSISTENT.
- If <50% of windows have PF > 1.0 → verdict: INCONSISTENT (performance clustered in specific periods).
- High variance between windows suggests time-dependency worth investigating.

---

## Out-of-sample validation

Split a backtest into an in-sample (IS) and out-of-sample (OOS) period and compare metrics.

```bash
# Split by date
python backtest/oos_split.py \
    --csv backtest/results/backtest_YYYYMMDD_HHMMSS.csv \
    --split 2026-03-01

# Split by percentage (70% IS, 30% OOS)
python backtest/oos_split.py \
    --csv backtest/results/backtest_YYYYMMDD_HHMMSS.csv \
    --pct 0.7
```

**How to interpret:**
- If OOS metrics are broadly similar to IS → edge is likely real.
- If OOS WR / PF / expectancy degrades >10% vs IS → potential overfit to the IS period.
- The script prints a `Verdict` line: STABLE / MILD degradation / DEGRADATION detected.

**Note:** Because this strategy uses fixed parameters from `.env` (not optimised per backtest
period), OOS degradation would reflect market non-stationarity rather than curve-fitting.

---

## Market regime analysis

The backtest CSV already contains a `market_phase` column (UPTREND / DOWNTREND / MIXED)
and a `vol_ratio` column. Use `analysis/regime.py` or filter the CSV directly:

```bash
# From Python — analyse existing CSV
python - <<'EOF'
import csv, sys
sys.path.insert(0, ".")
from analysis.metrics import compute_stats, segment_trades
from analysis.regime import add_regime_labels, regime_analysis, print_regime_report

with open("backtest/results/backtest_YYYYMMDD_HHMMSS.csv") as f:
    trades = list(csv.DictReader(f))

for t in trades:
    t["pnl_usdt"] = float(t["pnl_usdt"])
    t["vol_ratio"] = float(t.get("vol_ratio", 0))

report = regime_analysis(trades)
print_regime_report(report)
EOF
```

Regime dimensions:
- **Market phase** (EMA alignment): UPTREND / DOWNTREND / MIXED
- **Volatility** (vol_ratio ≥ 1.5 = HIGH_VOL, else LOW_VOL)
- **Combined**: e.g. UPTREND_HIGH_VOL

---

## Top-winner concentration

Section 12 of the backtest report already shows concentration for top 1/5/10/20 trades.
For more detail, use `analysis/metrics.py`:

```python
from analysis.metrics import top_winner_concentration
rows = top_winner_concentration(trades)
for r in rows:
    print(f"Top {r['n']:>2}: {r['pct_of_total']:+.1f}% of PnL | "
          f"Rest PF={r['stats_excl']['profit_factor']:.2f} "
          f"Exp={r['stats_excl']['expectancy']:+.3f}")
```

**Interpretation:**
- Top-5 > 70% of PnL → edge may be fragile (outlier-dependent).
- `stats_excl` with positive expectancy → edge exists beyond outliers.
- `stats_excl` with negative expectancy → removing outliers turns strategy unprofitable.

---

## Potential filter analysis

The `analysis_YYYYMMDD_HHMMSS.csv` segments performance across all key dimensions:
`interval`, `score_range`, `market_phase`, `vol_ratio`, `rsi_at_signal`, `ema_spread`,
`body_ratio`, `hour_utc`, `weekday`.

To identify consistently bad segments:
1. Open the analysis CSV in a spreadsheet.
2. Filter rows where `profit_factor < 1.0` and `total_trades > 5`.
3. Those segments are candidates for filtering.

**Any filter improvements must be tested in backtest first and enabled only via `.env`
flags — never automatically applied to the live bot.**

---

## Key parameters

| Parameter | Source | Default |
|---|---|---|
| TOP_SYMBOLS | `top_volume_symbols_count` in `config.py` | 300 |
| INTERVALS | Derived from `MAIN_INTERVAL`, `CONTEXT_INTERVAL` | 15m, 1h, 4h |
| MARGIN_PER_TRADE | `FIXED_MARGIN_PER_TRADE_USDT` | 5 USDT |
| LEVERAGE | `LEVERAGE` | 20x |
| MAX_CANDLES_HOLD | Hardcoded | 50 candles |

## Notes

- SELL trades are blocked on `4h` to mirror live long-only behaviour.
- Phase 1 download uses 60 parallel threads; Phase 2 simulation uses `cpu_count` processes.
- Rate limiter enforces Binance weight budget (2300 req/min).
- `statistics` module (stdlib) is the only dependency added in Stage 2.
