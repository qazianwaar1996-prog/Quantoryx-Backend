# Quantoryx — Testing Guide

Quantoryx ships a **pytest** suite covering unit, integration, and end-to-end
pipeline behavior. This guide explains how to run it and how to extend it.

---

## 1. Running the Suite

```bash
pip install -r requirements.txt   # pytest is included
pytest                            # run everything (config in pytest.ini)
pytest -v                         # verbose, per-test names
pytest tests/test_strategies.py   # a single file
pytest -k "confidence"            # tests matching an expression
```

Configuration lives in [`pytest.ini`](pytest.ini): `testpaths = tests`, concise
tracebacks, and deprecation-warning filtering.

**Expected result:** `39 passed` in ~30–35 s.

---

## 2. Test Taxonomy

| File | Type | Focus |
|---|---|---|
| `tests/test_unit_core.py` | Unit | `config` constants & `get_strategy_config`; indicators (bounds/ordering/length); `RiskManager` sizing, SL/TP, exposure gate; `ConfidenceModel` bounds & regime alignment; `param_ranges` combinations & constraints |
| `tests/test_strategies.py` | Unit | Registry wiring; the `signal ∈ {-1,0,1}` contract for **all 7** strategies (parametrized); column-case insensitivity; **parameter sensitivity** (distinct params ⇒ distinct signals); default fallback for partial params |
| `tests/test_integration.py` | Integration | `BacktestEngine` metric contract; **regime-reclassification skip**; optimizer ranking; walk-forward fold generation |
| `tests/test_pipeline.py` | End-to-end | Full `run_autonomous_pipeline` on synthetic data producing canonical report artifacts with correct schemas; **security** — `_safe_parse_params` never executes code |

---

## 3. Shared Fixtures (`tests/conftest.py`)

- **`ohlcv`** — small deterministic OHLCV frame (600 bars, seeded) for fast unit
  tests.
- **`ohlcv_pipeline`** — larger deterministic frame (2600 bars) sized for a
  couple of walk-forward folds.
- **`workdir`** — runs a test inside an isolated `tmp_path` (via `monkeypatch.chdir`)
  so file-writing code never pollutes the repo.

`conftest.py` also inserts the project root on `sys.path`, so tests run from any
working directory.

---

## 4. What the Tests Guard (Regression Anchors)

These tests exist specifically to prevent the v2.x defects from recurring:

- **Imports & wiring:** every core module imports and the strategy registry has
  all 7 strategies (guards the config-schema breakage that killed the pipeline).
- **Parameter sensitivity:** `test_ema_parameters_change_signals` fails if
  strategies ever silently collapse back to an identical fallback signal.
- **Regime performance:** `test_backtest_engine_skips_reclassification_when_tagged`
  fails if the O(combos × bars) regime hotspot is reintroduced.
- **Security:** `test_safe_parse_params_rejects_code_execution` fails if unsafe
  `eval()` returns to parameter parsing.
- **Report schemas:** the pipeline test asserts the exact columns the dashboard
  and validator depend on.

---

## 5. Writing New Tests

1. Put new tests under `tests/` named `test_*.py`.
2. Prefer the shared fixtures over ad-hoc data; keep new data seeded.
3. Use `workdir` for anything that writes files.
4. For a new strategy, no new test is required for the basic contract — the
   parametrized tests in `test_strategies.py` pick it up from the registry
   automatically. Add targeted tests for its unique logic.
5. Keep unit tests fast (sub-second); reserve heavier work for integration/
   pipeline tests using the larger fixture.

---

## 6. Continuous Validation (Runtime Health)

Beyond pytest, `python run_validation.py` performs a **live** system audit:
module-import verification, AST static analysis (unused imports / duplicate
lines), an end-to-end benchmark (time + peak memory), and a report-schema audit.
It writes `system_health_report.json` and `validation_log.csv`. Use it as a
runtime smoke test complementary to the unit suite.
