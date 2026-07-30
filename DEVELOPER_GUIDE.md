# Quantoryx — Developer Guide

Practical guidance for working on Quantoryx: environment setup, project
conventions, and common extension recipes.

---

## 1. Environment Setup

```bash
git clone <your-fork>
cd Quantoryx
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
pytest                                              # confirm a green baseline
python run_quantoryx.py                             # smoke-test the full pipeline
```

**Requirements:** Python 3.9+ (developed/tested on 3.12). Core deps: pandas,
numpy, matplotlib, seaborn, tabulate, streamlit; pytest for development.

---

## 2. Project Conventions

- **Configuration is centralized.** Never hard-code constants in a module —
  add them to `config.py` and import. Directory/paths go through
  `utils.path_manager.PathManager`, never raw string paths.
- **Logging over prints (for new code).** Use
  `from utils.logging_config import get_logger; logger = get_logger(__name__)`.
  Set verbosity with `QUANTORYX_LOG_LEVEL=DEBUG`.
- **OHLCV columns are lower-case** (`open, high, low, close, volume`) with a
  `DatetimeIndex`. Strategies must remain case-insensitive via
  `BaseStrategy._series()`.
- **Type hints & docstrings** on public functions/classes.
- **Determinism.** Keep synthetic data seeded; avoid wall-clock-dependent logic
  in core computations. Use timezone-aware datetimes when needed.
- **Backward compatibility.** Preserve the standard metric contract and report
  schemas (see `ARCHITECTURE.md §4`).

---

## 3. Recipe: Add a New Strategy

1. **Create** `strategies/my_strategy.py`:

   ```python
   import pandas as pd
   from engine.indicators import ema
   from strategies.base import BaseStrategy

   class MyStrategy(BaseStrategy):
       CONFIG_KEY = "MyStrategy"          # key into config.STRATEGY_DEFAULTS

       @property
       def name(self) -> str:
           return "my_strategy"

       def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
           period = int(self.get_param("period", 20))
           df["my_ind"] = ema(self._series(df, "close"), period)
           return df

       def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
           df["signal"] = 0
           df.loc[self._series(df, "close") > df["my_ind"], "signal"] = 1
           df.loc[self._series(df, "close") < df["my_ind"], "signal"] = -1
           return df
   ```

2. **Register** it in `strategies/__init__.py` (`STRATEGY_REGISTRY`).

3. **Add defaults** to `config.STRATEGY_DEFAULTS["MyStrategy"]`.

4. **Add a grid** to `optimizer/param_ranges.DEFAULT_RANGES["MyStrategy"]`
   (and a validity rule in `_is_valid_combination` if needed).

5. **Wire the engine mapping** (optional): add the display name to
   `BacktestEngine.STRATEGY_MAPPING` if you use a non-obvious CLI alias.

6. **Test:** the parametrized tests in `tests/test_strategies.py` automatically
   cover every registered strategy (signal contract + case-insensitivity).
   Run `pytest tests/test_strategies.py`.

---

## 4. Recipe: Add an Indicator

Add a vectorized function to `engine/indicators.py` operating on
`pd.Series`/`pd.DataFrame` and returning the same length. Add a unit test in
`tests/test_unit_core.py`.

---

## 5. Recipe: Change Where Files Are Written

Edit `PathManager.DIRECTORIES` in `utils/path_manager.py`. Every producer and
consumer (pipeline, dashboard, validator) resolves through `PathManager`, so a
single change is enough.

---

## 6. Running Individual Phases

Each pipeline phase has a standalone CLI (`run_*.py`) — handy for focused
iteration. Example:

```bash
python run_optimizer.py --strategy RSI --symbol EURUSD --timeframe 1H --metric sharpe_ratio
python run_walk_forward.py --strategy EMA --symbol EURUSD --timeframe 1H --train-days 90 --test-days 30
```

All runners auto-generate synthetic data if the target CSV is missing.

---

## 7. Debugging Tips

- **Verbose logs:** `QUANTORYX_LOG_LEVEL=DEBUG python run_quantoryx.py`.
- **Health audit:** `python run_validation.py` writes `system_health_report.json`
  with per-module import status, static-analysis findings, a benchmark, and a
  report-schema audit.
- **Isolate a strategy:** `python run_backtest.py --strategy MACD`.
- **Reproduce data:** `generate_synthetic_ohlcv(..., seed=<n>)` is deterministic.

---

## 8. Code Layout Summary

| Area | Where |
|---|---|
| Constants / defaults | `config.py` |
| Paths / directories | `utils/path_manager.py` |
| Logging | `utils/logging_config.py` |
| Indicators | `engine/indicators.py` |
| Backtest loop | `engine/backtest_engine.py` |
| Strategies | `strategies/` |
| Optimization | `optimizer/` |
| Walk-forward | `walk_forward/` |
| AI decisioning | `ai_engine/` |
| Risk / execution / portfolio | `risk/`, `paper_trading/`, `portfolio/` |
| Validation | `validation/pipeline_validator.py` |
| Tests | `tests/` |
