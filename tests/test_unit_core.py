"""Unit tests for the pure/computational core: config, indicators, risk,
confidence model, and optimizer parameter grids."""

import numpy as np
import pandas as pd
import pytest

import config
from ai_engine.confidence_model import ConfidenceModel
from engine import indicators as ind
from optimizer.param_ranges import DEFAULT_RANGES, generate_combinations
from risk.risk_manager import RiskManager


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------
def test_config_core_constants_present():
    assert config.SYSTEM_NAME == "Quantoryx"
    assert isinstance(config.DEFAULT_CAPITAL, float)
    assert set(config.RISK_LIMITS) >= {
        "risk_per_trade_pct", "max_daily_loss_pct", "max_total_drawdown_pct",
        "max_concurrent_trades", "max_exposure_per_pair_pct", "default_rr_ratio",
    }
    # Centralized market/directory constants added in v3.
    assert "EURUSD" in config.SUPPORTED_PAIRS
    assert config.PIP_SIZE["USDJPY"] == 0.01
    assert config.REPORTS_DIR and config.LOGS_DIR


def test_get_strategy_config_defaults_and_override():
    ema = config.get_strategy_config("EMA")
    assert ema["fast_period"] == 10 and ema["slow_period"] == 30
    # Override is type-coerced to the default's type.
    overridden = config.get_strategy_config("EMA", {"fast_period": "8"})
    assert overridden["fast_period"] == 8 and isinstance(overridden["fast_period"], int)


def test_get_strategy_config_unknown_raises():
    with pytest.raises(ValueError):
        config.get_strategy_config("NOPE")


# --------------------------------------------------------------------------
# indicators
# --------------------------------------------------------------------------
def test_ema_and_sma_lengths(ohlcv):
    close = ohlcv["close"]
    assert len(ind.ema(close, 10)) == len(close)
    assert len(ind.sma(close, 10)) == len(close)


def test_rsi_bounded(ohlcv):
    r = ind.rsi(ohlcv["close"], 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_macd_columns(ohlcv):
    m = ind.macd(ohlcv["close"])
    assert list(m.columns) == ["macd", "signal", "histogram"]


def test_bollinger_ordering(ohlcv):
    bb = ind.bollinger_bands(ohlcv["close"], 20, 2.0).dropna()
    assert (bb["upper"] >= bb["middle"]).all()
    assert (bb["middle"] >= bb["lower"]).all()


# --------------------------------------------------------------------------
# RiskManager
# --------------------------------------------------------------------------
def test_position_size_scales_with_risk():
    rm = RiskManager(risk_per_trade_pct=1.0)
    size = rm.calculate_position_size(balance=100_000, entry_price=1.10, stop_loss_price=1.09)
    assert size > 0
    # Zero stop distance is rejected safely.
    assert rm.calculate_position_size(100_000, 1.10, 1.10) == 0.0


def test_sl_tp_directions_and_rr():
    rm = RiskManager(default_rr_ratio=2.0)
    sl, tp = rm.calculate_sl_tp("LONG", 100.0, stop_loss_pct=1.0)
    assert sl < 100.0 < tp
    # TP distance is rr * SL distance.
    assert tp - 100.0 == pytest.approx((100.0 - sl) * 2.0, rel=1e-6)
    sl_s, tp_s = rm.calculate_sl_tp("SHORT", 100.0, stop_loss_pct=1.0)
    assert tp_s < 100.0 < sl_s


def test_exposure_gate_blocks_and_allows():
    rm = RiskManager(max_exposure_per_pair_pct=15.0, max_concurrent_trades=5)
    ok, _ = rm.evaluate_entry_allowance("EURUSD", 100_000, 0.0, 0.0, proposed_notional_size=5_000)
    assert ok
    blocked, msg = rm.evaluate_entry_allowance("EURUSD", 100_000, 0.0, 0.0, proposed_notional_size=20_000)
    assert not blocked and "exposure" in msg.lower()


# --------------------------------------------------------------------------
# ConfidenceModel
# --------------------------------------------------------------------------
def test_confidence_score_bounded():
    cm = ConfidenceModel()
    for regime in ("Trending", "Ranging", "High Volatility", "Low Volatility"):
        score = cm.compute_score("EMA", regime, oos_sharpe=1.5, oos_win_rate=0.55, oos_profit_factor=1.4)
        assert 0.0 <= score <= 100.0


def test_confidence_regime_alignment_matters():
    cm = ConfidenceModel()
    args = dict(oos_sharpe=1.5, oos_win_rate=0.55, oos_profit_factor=1.4)
    trending = cm.compute_score("EMA", "Trending", **args)
    ranging = cm.compute_score("EMA", "Ranging", **args)
    # A trend strategy should score higher in a trending regime than a range.
    assert trending > ranging


# --------------------------------------------------------------------------
# param_ranges
# --------------------------------------------------------------------------
def test_generate_combinations_respects_constraints():
    ema = generate_combinations("EMA")
    assert ema and all(c["fast_period"] < c["slow_period"] for c in ema)
    rsi = generate_combinations("RSI")
    assert all(c["oversold"] < c["overbought"] for c in rsi)


def test_all_default_ranges_generate_some_combos():
    for name in DEFAULT_RANGES:
        assert generate_combinations(name), f"{name} produced no combinations"
