# ============================================================
# strategies/breakout.py — Channel Breakout Strategy
# ============================================================
# Logic:
#   BUY  when price breaks ABOVE the prior N-bar high * breakout_factor
#   SELL when price breaks BELOW the prior N-bar low  / breakout_factor
# ============================================================

import pandas as pd

from engine.indicators import rolling_high, rolling_low
from strategies.base import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    """Volatility/trend channel breakout."""

    CONFIG_KEY = "Breakout"

    @property
    def name(self) -> str:
        return "breakout"

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        lookback = int(self.get_param("lookback_period", 20))
        high = self._series(df, "high")
        low = self._series(df, "low")
        # Shift so the current bar is compared against the *prior* window.
        df["breakout_high"] = rolling_high(high, lookback).shift(1)
        df["breakout_low"] = rolling_low(low, lookback).shift(1)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        factor = float(self.get_param("breakout_factor", 1.01))
        close = self._series(df, "close")
        df["signal"] = 0

        buy = close > df["breakout_high"] * factor
        sell = close < df["breakout_low"] / factor
        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df
