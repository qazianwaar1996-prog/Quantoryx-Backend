# Quantoryx v3.0

Quantoryx is a **local, self-contained quantitative trading research platform**. It
runs a complete systematic-research pipeline — market-regime detection,
walk-forward optimization, out-of-sample evaluation, explainable AI strategy
selection, risk-managed paper trading, and analytics — entirely on your machine
with **no broker APIs, cloud services, or external data feeds**.

> **v3.0 — Production Engineering Pass.** This release is an engineering-quality
> overhaul: the previously broken pipeline now runs end-to-end, the strategy
> layer is fully functional, the optimizer is ~11× faster, dead/duplicate code
> was removed, and a 39-test automated suite guards the whole system. See
> [`CHANGELOG.md`](CHANGELOG.md) and [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md).

---

## 1. Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the full autonomous pipeline (synthetic data is generated automatically)
python run_quantoryx.py --symbol EURUSD --timeframe 1H

# 3. Explore results in the local dashboard
python run_dashboard.py
```

The pipeline writes all artifacts to standardized folders (`reports/`, `logs/`,
`output/`) created on first run. With the bundled synthetic dataset the whole
pipeline completes in roughly **15–20 seconds**.

---

## 2. System Architecture

Quantoryx is a chronological pipeline: each stage's output configures the next.

```text
Historical OHLCV Data
  └── [Phase 1] Market-Regime Detection      (ADX · ATR · EMA slope · Bollinger width)
        └── [Phase 2] Walk-Forward Validation (rolling in-sample grid optimization)
              └── [Phase 3] AI Decision Engine (confidence scoring · explanation)
                    └── [Phase 4] Risk Gateways (drawdown · exposure · concurrency)
                          └── [Phase 5] Paper-Trading Simulator (leverage · spread · margin)
                                └── [Phase 6] Reporting & Analytics Dashboard
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for module-by-module detail and data flow.

---

## 3. Project Layout

```text
Quantoryx/
├── ai_engine/            # AI decision, confidence scoring, strategy selection, explanations
│   ├── confidence_model.py
│   ├── decision_engine.py
│   ├── explanation_engine.py
│   └── strategy_selector.py
├── dashboard/            # Streamlit analytics dashboard
│   └── app.py
├── engine/               # Core simulation
│   ├── backtest_engine.py  # Regime-aware bar-by-bar backtester
│   └── indicators.py       # Shared technical indicators (EMA, RSI, MACD, BB, ATR, ...)
├── market_regime/        # Regime detection & per-regime performance analysis
│   ├── detector.py
│   └── analyzer.py
├── optimizer/            # Grid-search hyper-parameter optimization
│   ├── optimizer_engine.py
│   └── param_ranges.py
├── paper_trading/        # Leverage/margin paper-trading simulator
│   └── paper_engine.py
├── portfolio/            # Capital-curve & portfolio KPI tracking
│   └── portfolio_manager.py
├── risk/                 # Position sizing & risk gateways
│   └── risk_manager.py
├── strategies/           # 7 pluggable strategies + registry
│   ├── base.py           # Abstract BaseStrategy (signal contract)
│   ├── ema_crossover.py  rsi.py  macd.py  bollinger.py
│   ├── breakout.py  support_resistance.py  trend_pullback.py
│   └── __init__.py       # STRATEGY_REGISTRY + get_strategy()
├── utils/                # Cross-cutting helpers
│   ├── generate_mock_data.py  # Synthetic OHLCV generator
│   ├── logging_config.py      # Centralized logging
│   └── path_manager.py        # Canonical directory/path resolution
├── validation/           # System health & pipeline validation
│   └── pipeline_validator.py
├── walk_forward/         # Rolling walk-forward validation engine
│   └── validation_engine.py
├── tests/                # Pytest unit / integration / pipeline suite
├── config.py             # Single source of truth for all constants
├── run_quantoryx.py      # Master orchestrator (single-command pipeline)
└── run_*.py              # Standalone CLI entry points per phase
```

---

## 4. Command-Line Entry Points

| Command | Purpose |
|---|---|
| `python run_quantoryx.py` | **Master** — the full autonomous pipeline |
| `python run_backtest.py --strategy EMA` | Single-strategy backtest |
| `python run_optimizer.py --strategy EMA --symbol EURUSD --timeframe 1H` | Grid optimization |
| `python run_walk_forward.py --strategy EMA --symbol EURUSD --timeframe 1H` | Walk-forward validation |
| `python run_market_regime.py` | Regime detection + per-regime analytics |
| `python run_ai_engine.py --symbol EURUSD --timeframe 1H` | AI decision-engine standalone |
| `python run_paper_trading.py --symbol EURUSD` | Paper-trading simulation |
| `python run_portfolio_analysis.py --symbol EURUSD` | Portfolio risk analysis |
| `python run_validation.py` | System health audit + end-to-end benchmark |
| `python run_dashboard.py` | Launch the Streamlit dashboard |

All runners auto-generate a synthetic dataset if none is present, so every
command works out of the box.

---

## 5. Configuration

All tunable values live in [`config.py`](config.py): system branding, default
capital/leverage/spread, `RISK_LIMITS`, `STRATEGY_DEFAULTS`, supported pairs and
timeframes, pip metadata, and canonical directory names. No module hard-codes
magic numbers — change behavior in one place.

Logging verbosity is controlled by the `QUANTORYX_LOG_LEVEL` environment
variable (`DEBUG`, `INFO`, `WARNING`, ...).

---

## 6. Testing

```bash
pip install -r requirements.txt   # includes pytest
pytest                            # 39 tests: unit + integration + end-to-end pipeline
```

See [`TESTING_GUIDE.md`](TESTING_GUIDE.md) for the test taxonomy and how to add
new tests.

---

## 7. Documentation Map

| Document | Contents |
|---|---|
| [`README.md`](README.md) | This overview & quick start |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Module responsibilities, data flow, extension points |
| [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md) | Setup, conventions, how to add a strategy |
| [`TESTING_GUIDE.md`](TESTING_GUIDE.md) | Test layout, fixtures, running & writing tests |
| [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) | Full v3.0 engineering-pass audit report |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history |

---

## 8. Disclaimer

Quantoryx is a **research and educational** framework. It trades only simulated
capital on historical/synthetic data and is **not** investment advice or a
live-trading system.
