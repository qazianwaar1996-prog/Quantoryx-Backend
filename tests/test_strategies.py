"""Unit tests for the strategy layer: registry wiring, the signal contract,
column-case robustness, and parameter sensitivity."""

import pandas as pd
import pytest

from strategies import STRATEGY_REGISTRY, all_strategies, get_strategy

STRATEGY_NAMES = list(STRATEGY_REGISTRY.keys())


def test_registry_has_seven_strategies():
    assert len(STRATEGY_REGISTRY) == 7


@pytest.mark.parametrize("name", STRATEGY_NAMES)
def test_strategy_emits_valid_signal_contract(name, ohlcv):
    strat = get_strategy(name)
    out = strat.run(ohlcv)
    assert "signal" in out.columns
    assert set(out["signal"].unique()).issubset({-1, 0, 1})
    assert len(out) == len(ohlcv)


@pytest.mark.parametrize("name", STRATEGY_NAMES)
def test_strategy_is_column_case_insensitive(name, ohlcv):
    """Strategies must accept Title-case frames (as the backtest engine feeds)."""
    title = ohlcv.rename(columns={c: c.title() for c in ohlcv.columns})
    strat = get_strategy(name)
    out = strat.run(title)
    assert set(out["signal"].unique()).issubset({-1, 0, 1})


def test_get_strategy_unknown_raises():
    with pytest.raises(ValueError):
        get_strategy("does_not_exist")


def test_all_strategies_returns_instances():
    strategies = all_strategies()
    assert len(strategies) == 7
    assert all(hasattr(s, "run") for s in strategies)


def test_ema_parameters_change_signals(ohlcv):
    """Distinct parameters must produce distinct signal series (proves that
    optimization is actually meaningful, not collapsed to a fixed fallback)."""
    fast = get_strategy("ema_crossover", {"fast_period": 5, "slow_period": 20}).run(ohlcv)["signal"]
    slow = get_strategy("ema_crossover", {"fast_period": 20, "slow_period": 100}).run(ohlcv)["signal"]
    assert not fast.equals(slow)


def test_defaults_fill_missing_params(ohlcv):
    """A partial override still works: missing keys fall back to config defaults."""
    out = get_strategy("rsi", {"period": 10}).run(ohlcv)  # oversold/overbought from config
    assert "rsi" in out.columns
    assert set(out["signal"].unique()).issubset({-1, 0, 1})
