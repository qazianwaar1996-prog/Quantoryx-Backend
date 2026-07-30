# Changelog

All notable changes to the **Quantoryx** algorithmic trading framework are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.0.0] - 2026-07-22 — Production Engineering Pass

A full engineering-quality overhaul that makes the previously non-functional
pipeline run end-to-end, without redesigning the architecture. See
[`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) for the complete audit.

### Fixed
*   **Pipeline-killing config contract.** Restored importability of the entire
    stack: the master pipeline previously aborted at Phase 2 with
    `ImportError: cannot import name 'SPREAD_PIPS' from 'config'`. All 19 modules
    now import; the pipeline completes all 6 phases.
*   **Strategy layer schema mismatch.** Rewrote `strategies/base.py` and all 7
    strategies to use the correct `STRATEGY_DEFAULTS` schema (`fast_period`,
    `period`, …), decoupled them from broken legacy imports, made them
    column-case robust, and enforced a `signal ∈ {-1,0,1}` contract. This
    eliminates the silent collapse to an identical dual-EMA fallback that made
    optimization meaningless.
*   **Missing method.** Implemented `BacktestEngine._generate_strategy_signals()`
    (called by the orchestrator's paper-trading phase; previously an
    `AttributeError`).
*   **Zero-trade paper engine.** Per-pair exposure is now measured as committed
    margin (notional / leverage) so orders on a leveraged account are no longer
    universally rejected. Applied consistently to `paper_trading` and
    `run_portfolio_analysis`.
*   **Unsafe `eval()`** on stringified parameters replaced with a hardened
    `ast.literal_eval`-based parser (`_safe_parse_params`).
*   **Report path mismatch.** Dashboard and validator now resolve report paths
    through `PathManager`; the pipeline emits a schema-correct
    `portfolio_report.csv` and a consolidated `walk_forward_report.csv`.
*   **Out-of-the-box data insufficiency.** The synthetic generator scales its
    regime cycle with length and produces ~1 year of data by default, so default
    walk-forward windows have enough history.
*   **`RuntimeWarning` in ADX** division guarded via `np.errstate`.

### Performance
*   Master pipeline runtime reduced from **>3 min to ~17 s (~11×)** via:
    regimes classified once per dataset (skipped inside optimizer combos), a
    NumPy-array backtest inner loop (no per-bar `.iloc`), and suppression of
    redundant per-combo disk writes (`write_reports=False`).

### Added
*   **`tests/`** — a 39-test pytest suite (unit + integration + end-to-end),
    plus `pytest.ini`.
*   **`utils/logging_config.py`** — centralized, level-configurable logging
    (`QUANTORYX_LOG_LEVEL`).
*   **Centralized constants** in `config.py`: `SUPPORTED_PAIRS`,
    `SUPPORTED_TIMEFRAMES`, `PIP_SIZE`, and canonical directory constants.
*   New/updated documentation: `README.md`, `ARCHITECTURE.md`,
    `DEVELOPER_GUIDE.md`, `TESTING_GUIDE.md`, `PROJECT_AUDIT.md`.

### Removed
*   Orphaned/broken/duplicate legacy "QuantPilot" modules: `engine/backtester.py`,
    `engine/risk.py`, `engine/data_loader.py`, `utils/logger.py`,
    `reports/{metrics,charts,ranking}.py`, `reports/__init__.py`,
    `generate_sample_data.py`, `optimizer/run_optimizer.py`, `data/test.py`.
*   Committed runtime artifacts (root `*.csv`, `system_health_report.json`,
    `validation_log.csv`) are now `.gitignore`d instead of tracked.

### Changed
*   `requirements.txt` re-branded; added `streamlit` and `pytest`.
*   Version bumped to `3.0.0`.

---

## [2.0.0] - 2026-07-22

### Added
*   **Central Path Manager (`utils/path_manager.py`)**: Introduced a consolidated path coordinator to standardize output structures and eliminate duplicate directory-creation code across modules [CHANGELOG].
*   **Central Config System (`config.py`)**: Created a centralized system settings file, establishing standard capital parameters, default leverage multipliers, transaction spreads, and global risk thresholds [CHANGELOG].
*   **System Health Audit Tool (`PROJECT_HEALTH.md`)**: Added a diagnostic overview documenting static analysis findings, benchmark runtimes, and validation metrics [CHANGELOG].
*   **Detailed Self-Audit Blueprint (`PROJECT_AUDIT.md`)**: Added an objective system audit tracing fixed dynamic imports, column normalization logic, and obsolete modules.

### Changed
*   **Complete System Branding Upgrades**: Renamed every legacy reference to "QuantPilot", "Forex Backtesting Engine", or "forex_bot" to **"Quantoryx"** across all project source files, terminal headers, comments, config variables, and reports [CHANGELOG].
*   **Standardized Output Directory Structures**: 
    *   Redirected transaction audit outputs from root to `output/trades/paper_trade_log.csv` [CHANGELOG].
    *   Redirected execution logs from root to `logs/ai_decision_log.csv` [CHANGELOG].
    *   Redirected final comparative reports to `reports/portfolio_report.csv` and `reports/paper_performance_report.csv` [CHANGELOG].
*   **Synchronized Master Orchestration (`run_quantoryx.py`)**: Fully integrated the pipeline with `config.py` constants and routed files dynamically via `PathManager` [CHANGELOG].

### Fixed
*   **Dynamic Strategy Loading Failure**: Resolved a critical dynamic import bug inside `BacktestEngine._load_strategy` by linking strategy class generation directly to `strategies.STRATEGY_REGISTRY` and `get_strategy()`, preventing silent fallbacks to dual EMA signals.
*   **Case-Sensitivity Mismatches**: Standardized dataset ingestion column naming inside `run_quantoryx.py` by converting headers to lowercase prior to indicator calculation, resolving index-matching runtime errors.
*   **Unused Module Warnings**: Removed flagged unused imports (such as `itertools` and `json` inside optimization modules) identified by the AST static parser [CHANGELOG].
*   **Directory Creation Conflicts**: Resolved OS-level file and folder permission crashes on Unix-based backtesting instances by standardizing the `PathManager.resolve_path` pipeline [CHANGELOG].
*   **Inconsistent Trade Schema Layouts**: Corrected minor mismatches inside export column headers to guarantee backward compatibility with earlier CSV validation steps [CHANGELOG].

---

## [1.5.0] - 2026-06-30

### Added
*   **Phase 8 AI Decision Engine**: Introduced multi-factor confidence evaluation matrices to score strategies relative to active market regimes [CHANGELOG].
*   **Phase 6 Paper Trading Module**: Replicated real-time order executions incorporating virtual leverage structures, spreads, and margin calls [CHANGELOG].
*   **Phase 5 Risk Gateways**: Configured risk limits, single-asset exposure caps, and concurrent trade ceilings [CHANGELOG].

---

## [1.0.0] - 2026-04-15

### Added
*   **Base Backtester**: Initial local version. Provided chronological bar-by-bar backtesting, dynamic signal generation, and basic metric calculations (Sharpe, profit factor, max drawdown, and win rate).
*   **Grid Parameter Optimization**: Created search space iterators to evaluate performance matrices across parameter grids [CHANGELOG].
*   **Market Regime Detection**: Introduced ADX, ATR, EMA, and Bollinger Band indicators to categorize market volatility and trend profiles [CHANGELOG].
