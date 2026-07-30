# Quantoryx — Architecture

This document describes the module responsibilities, data flow, and extension
points of the Quantoryx platform. It reflects the consolidated **v3.0**
architecture (a single, coherent pipeline; the legacy "QuantPilot" subsystem was
removed — see [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md)).

---

## 1. Design Principles

1. **Single source of truth for configuration.** Every constant lives in
   `config.py`. Modules import what they need; nothing hard-codes magic numbers.
2. **Chronological pipeline.** Each phase consumes the previous phase's output.
   Stages are independently runnable via their `run_*.py` entry points.
3. **Deterministic & local.** No network calls. Synthetic data is reproducible
   (seeded). Runs are repeatable.
4. **Regimes computed once.** Market-regime labels are parameter-independent, so
   they are computed a single time per dataset and reused across every optimizer
   evaluation (a major performance property — see §5).
5. **Strategies are pure signal generators.** They read OHLC and emit a discrete
   `signal` column; execution/risk/accounting live in dedicated layers.

---

## 2. Layered Module Map

```
                        ┌───────────────────────────┐
                        │        config.py          │  constants / defaults
                        └────────────┬──────────────┘
                                     │ (imported everywhere)
        ┌────────────────────────────┼─────────────────────────────┐
        │                            │                             │
┌───────▼────────┐        ┌──────────▼─────────┐        ┌──────────▼─────────┐
│  utils/        │        │  engine/           │        │  market_regime/    │
│  path_manager  │        │  indicators        │        │  detector          │
│  logging_config│        │  backtest_engine ──┼───────►│  analyzer          │
│  generate_mock │        └──────────┬─────────┘        └────────────────────┘
└────────────────┘                   │ uses
                          ┌──────────▼─────────┐
                          │  strategies/       │  BaseStrategy + 7 strategies
                          │  (STRATEGY_REGISTRY)│
                          └──────────┬─────────┘
                                     │
        ┌────────────────────────────┼─────────────────────────────┐
┌───────▼────────┐        ┌──────────▼─────────┐        ┌──────────▼─────────┐
│  optimizer/    │───────►│  walk_forward/     │───────►│  ai_engine/        │
│  optimizer_eng │        │  validation_engine │        │  decision_engine   │
│  param_ranges  │        └────────────────────┘        │  confidence_model  │
└────────────────┘                                       │  strategy_selector │
                                                          │  explanation_engine│
                                                          └──────────┬─────────┘
                        ┌────────────────────────────────────────────┘
             ┌──────────▼─────────┐   ┌────────────────┐   ┌────────────────┐
             │  risk/             │──►│ paper_trading/ │──►│ portfolio/     │
             │  risk_manager      │   │ paper_engine   │   │ portfolio_mgr  │
             └────────────────────┘   └────────────────┘   └────────────────┘
                                     │
                          ┌──────────▼─────────┐   ┌────────────────────┐
                          │  reporting (CSVs)  │──►│  dashboard/app.py  │
                          └────────────────────┘   └────────────────────┘
```

---

## 3. Module Responsibilities

### Configuration & utilities
- **`config.py`** — Branding/version, `DEFAULT_*` account settings, `RISK_LIMITS`,
  `STRATEGY_DEFAULTS`, `SUPPORTED_PAIRS`/`SUPPORTED_TIMEFRAMES`, `PIP_SIZE`,
  canonical directory constants, and `get_strategy_config()`.
- **`utils/path_manager.py`** — `PathManager` resolves every output path to a
  standardized directory (`reports/`, `logs/`, `output/trades/`,
  `output/optimization/`, `config/optimized/`). The single authority on *where
  files go*.
- **`utils/logging_config.py`** — `get_logger()` provides a shared, namespaced,
  level-configurable logger (`QUANTORYX_LOG_LEVEL`).
- **`utils/generate_mock_data.py`** — Reproducible synthetic OHLCV with cycling
  regimes; sized so the default walk-forward windows always have enough history.

### Core engine
- **`engine/indicators.py`** — Vectorized technical indicators (EMA, SMA, RSI,
  MACD, Bollinger Bands, ATR, rolling high/low). Shared by all strategies.
- **`engine/backtest_engine.py`** — `BacktestEngine`: regime-aware, bar-by-bar
  simulator. Loads a strategy from the registry, generates signals, simulates
  entries/exits, and returns the standard metric contract (`net_profit`,
  `profit_factor`, `max_drawdown`, `win_rate`, `sharpe_ratio`). Skips regime
  reclassification when the frame is already tagged, and can suppress per-run
  file writes during optimization sweeps (`write_reports=False`).

### Strategies
- **`strategies/base.py`** — `BaseStrategy` abstract contract: `CONFIG_KEY`,
  `name`, `prepare()`, `generate_signals()`, plus helpers (`get_param()` with
  config-default fallback, case-insensitive `_series()`).
- **7 strategies** — EMA crossover, RSI, MACD, Bollinger, Breakout,
  Support/Resistance, Trend-Pullback. Each emits `signal ∈ {-1, 0, 1}`.
- **`strategies/__init__.py`** — `STRATEGY_REGISTRY`, `get_strategy()`,
  `all_strategies()`.

### Regime, optimization, validation
- **`market_regime/detector.py`** — Classifies each bar into Trending / Ranging /
  High-Vol / Low-Vol / Normal using ADX, ATR%, EMA slope, and BB width.
- **`market_regime/analyzer.py`** — Per-regime trade-performance KPIs.
- **`optimizer/param_ranges.py`** — Per-strategy grid definitions + validity
  constraints (e.g. `fast_period < slow_period`).
- **`optimizer/optimizer_engine.py`** — Grid search over combinations; ranks by a
  chosen primary metric; exports CSVs and the best-parameter JSON.
- **`walk_forward/validation_engine.py`** — Rolling in-sample optimization →
  out-of-sample evaluation across generated windows.

### AI decision layer
- **`ai_engine/confidence_model.py`** — Deterministic 0–100 confidence blending
  OOS performance (60%) with regime-compatibility (40%).
- **`ai_engine/strategy_selector.py`** — Ranks candidates, nominates a champion.
- **`ai_engine/explanation_engine.py`** — Human-readable justification text.
- **`ai_engine/decision_engine.py`** — Orchestrates the above; applies the
  confidence threshold (EXECUTE/SKIP); logs decisions.

### Execution, risk, portfolio, reporting
- **`risk/risk_manager.py`** — Position sizing, SL/TP, and account gateways
  (drawdown, daily loss, concurrency, per-pair exposure). Exposure is tracked in
  **committed-margin** units (see [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md)).
- **`paper_trading/paper_engine.py`** — Leverage/spread/margin simulator with
  margin-call & stop-out handling.
- **`portfolio/portfolio_manager.py`** — Equity-curve snapshots, drawdown,
  Sharpe, and portfolio KPIs.
- **`dashboard/app.py`** — Streamlit UI reading canonical report CSVs via
  `PathManager`.
- **`validation/pipeline_validator.py`** — Module-import checks, AST static
  analysis, an end-to-end benchmark, and a report-schema audit → JSON health
  report.

---

## 4. Data Contracts

**OHLCV frames** use lower-case columns (`open, high, low, close, volume`) with a
`DatetimeIndex`. Strategies are case-insensitive and also accept Title-case.

**Strategy output** must contain a `signal` column (`1`=long, `-1`=short,
`0`=flat).

**Backtest metrics** are always the dict:
`{net_profit, profit_factor, max_drawdown, win_rate, sharpe_ratio}`.

**Report schemas** (validated by `pipeline_validator`):
- `reports/portfolio_report.csv` → `date, balance, equity, drawdown_pct`
- `reports/walk_forward_report.csv` → `strategy, fold, train_start, …, oos_sharpe_ratio`
- `output/trades/paper_trade_log.csv` → `symbol, direction, entry_time, exit_time, pnl, …`
- `logs/ai_decision_log.csv` → `timestamp, symbol, selected_strategy, confidence_score, …`

---

## 5. Performance Characteristics

- **Regime classification is O(n) once per dataset.** `BacktestEngine` reuses
  pre-tagged frames, so an optimizer sweep of *k* parameter combinations does
  **not** recompute regimes *k* times.
- **The backtest inner loop iterates NumPy arrays**, not `DataFrame.iloc[i]`,
  turning each backtest into a tight numeric loop. Combined with the point
  above, the full master pipeline runs in ~15–20 s on the synthetic dataset
  (down from >3 min pre-optimization).
- **Optimizer sweeps suppress per-run disk writes** (`write_reports=False`),
  eliminating thousands of redundant CSV writes.

---

## 6. Extension Points

- **Add a strategy:** implement a `BaseStrategy` subclass, register it in
  `strategies/__init__.py`, add defaults to `config.STRATEGY_DEFAULTS`, and a grid
  to `optimizer/param_ranges.py`. See [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md).
- **Add an indicator:** add a vectorized function to `engine/indicators.py`.
- **Change output locations:** update `PathManager.DIRECTORIES` — all callers
  follow automatically.
- **Tune risk/behavior:** edit `config.py`.
