"""End-to-end pipeline test.

Runs the full autonomous pipeline on a small synthetic dataset inside an
isolated working directory and asserts that the canonical report artifacts
are produced with the schemas the dashboard and validator expect.
"""

import os

import pandas as pd
import pytest


def test_autonomous_pipeline_end_to_end(ohlcv_pipeline, workdir):
    # Arrange: write the dataset where the pipeline expects it.
    os.makedirs("data", exist_ok=True)
    data_path = os.path.join("data", "EURUSD_1H.csv")
    ohlcv_pipeline.to_csv(data_path)

    from run_quantoryx import run_autonomous_pipeline
    from utils.path_manager import PathManager

    # Act: short windows keep the test fast but still exercise every phase.
    run_autonomous_pipeline(
        symbol="EURUSD", timeframe="1H", data_path=data_path,
        starting_capital=100_000.0, train_days=40, test_days=15,
        leverage=30.0, spread=0.0002, confidence_threshold=0.0,
    )

    # Assert: canonical artifacts exist with the expected schema.
    wf = PathManager.resolve_path("reports", "walk_forward_report.csv")
    ai_log = PathManager.resolve_path("logs", "ai_decision_log.csv")
    assert os.path.exists(wf), "walk-forward report missing"
    assert os.path.exists(ai_log), "AI decision log missing"

    wf_df = pd.read_csv(wf)
    assert {"strategy", "fold", "oos_sharpe_ratio"}.issubset(wf_df.columns)

    portfolio = PathManager.resolve_path("reports", "portfolio_report.csv")
    if os.path.exists(portfolio):
        cols = set(pd.read_csv(portfolio, nrows=0).columns)
        assert {"date", "balance", "equity", "drawdown_pct"}.issubset(cols)


def test_safe_parse_params_rejects_code_execution():
    """The parameter parser must never execute arbitrary code (no eval)."""
    from run_quantoryx import _safe_parse_params

    assert _safe_parse_params("{'a': 1, 'b': 2}") == {"a": 1, "b": 2}
    assert _safe_parse_params({"x": 5}) == {"x": 5}
    # Malicious / malformed input degrades gracefully to an empty dict.
    assert _safe_parse_params("__import__('os').system('echo hacked')") == {}
    assert _safe_parse_params("not a dict") == {}
    assert _safe_parse_params("") == {}
