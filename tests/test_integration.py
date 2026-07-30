"""Integration tests wiring multiple components together: the backtest
engine, the optimizer grid search, and walk-forward validation."""

import pandas as pd
import pytest

from engine.backtest_engine import BacktestEngine
from market_regime.detector import MarketRegimeDetector

METRIC_KEYS = {"net_profit", "profit_factor", "max_drawdown", "win_rate", "sharpe_ratio"}


def test_backtest_engine_returns_metric_contract(ohlcv, workdir):
    engine = BacktestEngine(ohlcv, "EMA", {"fast_period": 10, "slow_period": 30})
    metrics = engine.run()
    assert METRIC_KEYS.issubset(metrics)
    assert isinstance(metrics["net_profit"], float)


def test_backtest_engine_skips_reclassification_when_tagged(ohlcv, workdir):
    """If regimes are already present, the engine must not recompute them."""
    tagged = MarketRegimeDetector().classify_regimes(ohlcv)
    calls = {"n": 0}
    engine = BacktestEngine(tagged, "RSI", {})
    original = engine.detector.classify_regimes

    def _spy(df):
        calls["n"] += 1
        return original(df)

    engine.detector.classify_regimes = _spy
    engine.run()
    assert calls["n"] == 0  # pre-tagged frame → no reclassification


def test_optimizer_ranks_results(ohlcv_pipeline, workdir):
    from optimizer.optimizer_engine import OptimizerEngine

    opt = OptimizerEngine("EMA", "EURUSD", "1H", ohlcv_pipeline, primary_metric="sharpe_ratio")
    ranked = opt.run_optimization()
    assert ranked, "optimizer returned no results"
    # Ranks are assigned 1..N in order.
    assert ranked[0]["rank"] == 1
    assert [r["rank"] for r in ranked] == sorted(r["rank"] for r in ranked)


def test_walk_forward_produces_folds(ohlcv_pipeline, workdir):
    from walk_forward.validation_engine import WalkForwardValidator

    tagged = MarketRegimeDetector().classify_regimes(ohlcv_pipeline)
    wfv = WalkForwardValidator(
        strategy_name="EMA", symbol="EURUSD", timeframe="1H",
        data_df=tagged, train_days=40, test_days=15, primary_metric="sharpe_ratio",
    )
    results = wfv.run_validation()
    assert results, "walk-forward produced no folds"
    row = results[0]
    assert {"fold", "oos_sharpe_ratio", "is_sharpe_ratio", "parameters"}.issubset(row)
