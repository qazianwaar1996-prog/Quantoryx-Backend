# ============================================================
# engine/indicators.py — All Technical Indicators
# ============================================================

import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index.
    Returns values between 0–100.
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    MACD — returns (macd_line, signal_line, histogram) as a DataFrame.
    """
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({
        "macd":      macd_line,
        "signal":    signal_line,
        "histogram": histogram,
    })


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """
    Bollinger Bands — returns (upper, middle, lower) as a DataFrame.
    """
    middle = sma(series, period)
    std    = series.rolling(window=period).std()
    upper  = middle + std_dev * std
    lower  = middle - std_dev * std
    return pd.DataFrame({
        "upper":  upper,
        "middle": middle,
        "lower":  lower,
    })


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range.
    df must have High, Low, Close columns.
    """
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]

    tr = pd.DataFrame({
        "hl":  high - low,
        "hpc": (high - close.shift(1)).abs(),
        "lpc": (low  - close.shift(1)).abs(),
    }).max(axis=1)

    return tr.ewm(com=period - 1, adjust=False).mean()


def rolling_high(series: pd.Series, lookback: int) -> pd.Series:
    """Rolling maximum over lookback periods."""
    return series.rolling(window=lookback).max()


def rolling_low(series: pd.Series, lookback: int) -> pd.Series:
    """Rolling minimum over lookback periods."""
    return series.rolling(window=lookback).min()


def support_resistance_zones(df: pd.DataFrame, lookback: int = 50, zone_pips: float = 0.0010):
    """
    Identify support and resistance zones from swing highs/lows.
    Returns a list of (level, type) tuples where type is 'support' or 'resistance'.
    """
    highs = df["High"].values
    lows  = df["Low"].values
    zones = []

    for i in range(lookback, len(df)):
        window_highs = highs[i - lookback:i]
        window_lows  = lows[i  - lookback:i]

        resistance = max(window_highs)
        support    = min(window_lows)

        zones.append({
            "index":      i,
            "resistance": resistance,
            "support":    support,
        })

    return pd.DataFrame(zones).set_index("index") if zones else pd.DataFrame()
