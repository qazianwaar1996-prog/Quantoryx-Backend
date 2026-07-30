# ============================================================
# strategies/trend_pullback.py — Trend + Pullback Strategy
# ============================================================
# Logic:
#   In an UPTREND   (close > trend EMA): BUY when RSI dips to the trigger
#   In a DOWNTREND  (close < trend EMA): SELL when RSI pops to (100 - trigger)
# ============================================================

import pandas as pd

from engine.indicators import ema, rsi as calc_rsi
from strategies.base import BaseStrategy


class TrendPullbackStrategy(BaseStrategy):
    """Trend-aligned pullback entries filtered by an EMA regime."""

    CONFIG_KEY = "TrendPullback"

    @property
    def name(self) -> str:
        return "trend_pullback"

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        trend_period = int(self.get_param("trend_period", 100))
        rsi_period = int(self.get_param("pullback_rsi_period", 14))
        close = self._series(df, "close")
        df["tp_trend_ema"] = ema(close, trend_period)
        df["tp_rsi"] = calc_rsi(close, rsi_period)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        trigger = float(self.get_param("pullback_rsi_trigger", 35.0))
        close = self._series(df, "close")
        df["signal"] = 0

        prev_rsi = df["tp_rsi"].shift(1)
        uptrend = close > df["tp_trend_ema"]
        downtrend = close < df["tp_trend_ema"]

        # Uptrend pullback: RSI crosses down through the trigger → BUY.
        buy = uptrend & (prev_rsi > trigger) & (df["tp_rsi"] <= trigger)
        # Downtrend pullback: RSI crosses up through the mirror trigger → SELL.
        upper_trigger = 100.0 - trigger
        sell = downtrend & (prev_rsi < upper_trigger) & (df["tp_rsi"] >= upper_trigger)
        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df
