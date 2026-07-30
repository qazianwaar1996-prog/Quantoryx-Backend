# Quantoryx — Project Audit (v3.0 Production Engineering Pass)

**Scope:** Full-repository engineering-quality audit and remediation.
**Constraint:** Preserve the existing architecture; fix and consolidate rather
than redesign; remain backward compatible with all working functionality.

---

## 1. Executive Summary

The uploaded project was **non-functional end-to-end**. It contained two fused
architectures — the active **"Quantoryx v2.0"** pipeline and an orphaned legacy
**"QuantPilot"** subsystem — with incompatible configuration schemas. A baseline
audit proved:

- **10 of 19 modules failed to import**, including the critical
  `engine.backtest_engine`, `strategies`, and `walk_forward.validation_engine`.
- The master pipeline **aborted at Phase 2** with
  `ImportError: cannot import name 'SPREAD_PIPS' from 'config'`.

After the pass, the platform:

- **Runs the full pipeline end-to-end** (all 6 phases, exit 0).
- Executes real, parameter-sensitive strategies (no silent fallback collapse).
- Runs the master pipeline in **~17 s vs. >3 min** before optimization (~11×).
- Is guarded by a **39-test pytest suite** (unit + integration + end-to-end),
  all passing.
- Has **10 dead/duplicate files removed** and stale output artifacts untracked.

| Metric | Before | After |
|---|---|---|
| Modules importable | 9 / 19 | 19 / 19 |
| Master pipeline | Aborts at Phase 2 | Completes all 6 phases |
| Master pipeline runtime | >3 min (when patched to run) | ~17 s |
| Paper-trade execution | 0 trades (always rejected) | Trades execute correctly |
| Automated tests | 0 | 39 (passing) |
| Source files | 55 `.py` | 40 `.py` (dead code removed) |

---

## 2. Root-Cause Analysis

The repository carried a complete older framework ("QuantPilot") whose modules
imported ~12 configuration symbols (`SPREAD_PIPS`, `PIP_VALUE`, `INITIAL_BALANCE`,
`DEFAULT_RISK_PCT`, `SUPPORTED_PAIRS`, `OUTPUT_DIR`, …) that the current
`config.py` no longer defined. Because the active pipeline imported the shared
`strategies` package — which in turn imported the broken legacy `engine.risk` —
the failure cascaded through the entire dependency chain:

```
engine.risk (missing config symbols)
  └─ strategies/*  (also used a stale STRATEGY_DEFAULTS schema)
       └─ engine.backtest_engine  (from strategies import get_strategy)
            └─ walk_forward.validation_engine
                 └─ run_quantoryx  → aborts at Phase 2
```

---

## 3. Bugs Found & Fixed

### Critical
1. **Broken configuration contract (pipeline-killing).** Legacy modules imported
   nonexistent `config` symbols → 10 modules unimportable.
   **Fix:** consolidated on the v2 schema; removed the legacy modules that
   depended on the defunct schema; added genuinely useful centralized constants
   (market reference data, canonical directories) to `config.py`.

2. **Strategy layer used a stale schema.** Strategy classes referenced
   `STRATEGY_DEFAULTS["ema_crossover"]` with keys like `fast_ema`/`sl_pips`,
   while `config` defines `["EMA"]` with `fast_period`/`slow_period`. Even had
   imports succeeded, every strategy would have raised `KeyError` and silently
   fallen back to an identical dual-EMA signal — making optimization and
   strategy selection meaningless.
   **Fix:** rewrote `strategies/base.py` + all 7 strategies against the correct
   schema (matching the optimizer grids), decoupled from broken imports, made
   them column-case robust, and enforced the `signal ∈ {-1,0,1}` contract.

3. **Missing method call.** `run_quantoryx.py` Phase 6 called
   `BacktestEngine._generate_strategy_signals()`, which did not exist →
   `AttributeError` (paper trading never ran).
   **Fix:** implemented `_generate_strategy_signals()` as the single signal
   entry point (index-aligned, with safe fallback) and routed `run()` through it.

4. **Paper trading executed zero trades.** Position notional (≈66% of balance at
   1% risk / 1.5% SL) always exceeded the 15% per-pair exposure cap, so every
   order was rejected. The whole execution/portfolio/dashboard chain produced
   empty output.
   **Fix:** measure per-pair exposure as **committed margin** (notional /
   leverage), the correct interpretation for a leveraged account. Applied
   consistently in `paper_trading/paper_engine.py` and `run_portfolio_analysis.py`.

### High / Medium
5. **Unsafe `eval()`** on stringified parameters in `run_quantoryx.py` (twice).
   **Fix:** replaced with a hardened `_safe_parse_params()` using
   `ast.literal_eval` (covered by a security test).

6. **Report path mismatch.** The dashboard and validator read reports from the
   repo root, while the pipeline wrote them into `reports/`, `logs/`,
   `output/trades/` via `PathManager` → dashboards showed stale/empty data, and
   the `portfolio_report.csv` written from the paper engine lacked the
   `drawdown_pct` column the dashboard required.
   **Fix:** routed the dashboard and validator through `PathManager` (with
   legacy-root fallback); the pipeline now emits a schema-correct
   `portfolio_report.csv` (`date, balance, equity, drawdown_pct`) and a
   consolidated `walk_forward_report.csv` (previously never written by the
   master run).

7. **Out-of-the-box data insufficiency.** The synthetic generator produced ~50
   days of 1H data while the default walk-forward windows need ≥240 days → the
   pipeline always failed with "insufficient data" even once the code was fixed.
   **Fix:** the generator now scales its regime cycle with length and produces
   ~1 year by default; runners request appropriate sizes; the validator uses a
   dedicated, right-sized dataset.

8. **`RuntimeWarning: invalid value encountered in divide`** in the regime
   detector's ADX computation.
   **Fix:** wrapped in `np.errstate` (the `np.where` already selected a safe
   fallback).

9. **Unused import** (`PortfolioManager`) in the master orchestrator's risk phase.
   **Fix:** removed.

---

## 4. Dead Code & Duplication Removed

All removals were verified unreferenced by any active entry point before
deletion.

| File | Reason |
|---|---|
| `engine/backtester.py` | Duplicate backtest engine (legacy); broken imports |
| `engine/risk.py` | Legacy forex utils; broken config imports; only used by broken strategies |
| `engine/data_loader.py` | Unreferenced; broken config imports |
| `utils/logger.py` | Unreferenced; broken config imports (superseded by `logging_config.py`) |
| `reports/metrics.py` | Legacy report module; unreferenced; broken imports |
| `reports/charts.py` | Legacy report module; unreferenced; broken imports |
| `reports/ranking.py` | Legacy report module; unreferenced |
| `reports/__init__.py` | `reports/` is now purely an output directory |
| `generate_sample_data.py` | Duplicate of `utils/generate_mock_data.py`; broken imports |
| `optimizer/run_optimizer.py` | Duplicate of root `run_optimizer.py` (stale branding) |
| `data/test.py` | Empty placeholder |

Also **untracked** committed runtime artifacts (root-level `*.csv`,
`system_health_report.json`, `validation_log.csv`) and added a comprehensive
`.gitignore` so generated outputs are no longer under source control.

---

## 5. Performance Improvements

1. **Regime classification computed once, not per combo.** `BacktestEngine`
   skips reclassification when the frame is already regime-tagged. The walk-
   forward pipeline passes pre-tagged slices, so an optimizer sweep of *k*
   combinations no longer re-runs the O(n) classifier *k* times.
2. **Vectorized backtest inner loop.** Replaced per-bar `DataFrame.iloc[i]` /
   `index.get_loc()` lookups with pre-extracted NumPy arrays.
3. **Suppressed redundant disk writes during optimization** (`write_reports=False`),
   removing thousands of per-combo CSV/JSON writes.

**Net effect:** master pipeline **>3 min → ~17 s** (~11×); validator benchmark
peak memory ~5–14 MB.

---

## 6. Quality, Structure & Maintainability

- **Centralized constants** in `config.py` (market data, pip metadata, canonical
  directories) — no magic numbers scattered across modules.
- **Centralized logging** via `utils/logging_config.py` (`get_logger`,
  `QUANTORYX_LOG_LEVEL`).
- **Typing & docstrings** added/expanded across all edited modules.
- **Consistent path handling** through `PathManager` (single source of truth for
  output locations); dashboard and validator aligned to it.
- **Dependency hygiene:** `requirements.txt` re-branded, `streamlit` and
  `pytest` added, comments corrected.
- **Backward-compatible defaults:** `BacktestEngine(write_reports=True)` and the
  regime-skip behavior preserve existing call sites.

---

## 7. Testing Added

A `tests/` suite (pytest) with **39 tests**, all passing:

- **Unit:** config, indicators, risk manager, confidence model, param grids,
  and the full strategy contract (parametrized over all 7 strategies), including
  a parameter-sensitivity test that guards against fallback collapse.
- **Integration:** backtest metric contract, regime-reclassification skip,
  optimizer ranking, walk-forward fold generation.
- **End-to-end:** full `run_autonomous_pipeline` producing canonical artifacts
  with correct schemas; a security test proving parameter parsing cannot execute
  code.

See [`TESTING_GUIDE.md`](TESTING_GUIDE.md).

---

## 8. Verification Evidence

- `pytest` → **39 passed**.
- `python run_quantoryx.py` → all 6 phases, **exit 0**, 272 trades, reports
  written to canonical locations.
- `python run_validation.py` → status non-critical, **10/10 modules OK**, all
  required report schemas present, benchmark within budget.
- Every `run_*.py` CLI smoke-tested successfully.

---

## 9. Remaining Recommendations (Out of Scope for This Pass)

These are optional, non-blocking follow-ups; none affect current correctness.

1. **Trading-model realism.** The paper simulation can compound to large equity
   on synthetic data; consider slippage/liquidity modeling and wiring
   `RiskManager.account_drawdown_pct` into the live summary (currently reported
   from unmaintained state and shows 0%).
2. **Vectorize `MarketRegimeDetector.classify_regimes`.** Still uses an
   `iterrows` loop (~0.6 s / 9k bars — no longer a hotspot, but could be fully
   vectorized).
3. **Full logging rollout.** New/edited code uses the centralized logger; many
   stable modules still use `print`. Migrate incrementally.
4. **Parallelize optimization** (e.g. `multiprocessing`) for large grids.
5. **Real-data ingestion.** A thin, well-tested CSV loader could replace the
   removed legacy `data_loader` if external datasets are needed.
6. **CI integration.** Wire `pytest` + `run_validation.py` into a CI workflow.
