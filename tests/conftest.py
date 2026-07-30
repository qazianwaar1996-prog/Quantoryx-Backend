"""Shared pytest fixtures and path setup for the Quantoryx test suite."""

import os
import sys

import pandas as pd
import pytest

# Make the project root importable regardless of the pytest invocation cwd.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.generate_mock_data import generate_synthetic_ohlcv  # noqa: E402


@pytest.fixture(scope="session")
def ohlcv() -> pd.DataFrame:
    """A small, deterministic OHLCV frame (lower-case columns) for unit tests."""
    return generate_synthetic_ohlcv(symbol="EURUSD", timeframe="1H", bars=600, seed=7)


@pytest.fixture(scope="session")
def ohlcv_pipeline() -> pd.DataFrame:
    """A larger deterministic frame sized for a couple of walk-forward folds."""
    return generate_synthetic_ohlcv(symbol="EURUSD", timeframe="1H", bars=2600, seed=11)


@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    """Run a test inside an isolated temp directory (for file-writing paths)."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
