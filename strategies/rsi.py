# ============================================================
# strategies/rsi.py — RSI Mean-Reversion Strategy
# ============================================================
# Logic:
#   BUY  when RSI crosses back ABOVE the oversold level
#   SELL when RSI crosses back BELOW the overbought level
# ============================================================

import pandas as pd

from engine.indicators import rsi as calc_rsi
from strategies.base import BaseStrategy


class RSIStrategy(BaseStrategy):
    """Counter-trend RSI reversion."""

    CONFIG_KEY = "RSI"

    @property
    def name(self) -> str:
        return "rsi"

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        period = int(self.get_param("period", 14))
        df["rsi"] = calc_rsi(self._series(df, "close"), period)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        oversold = float(self.get_param("oversold", 30.0))
        overbought = float(self.get_param("overbought", 70.0))

        df["signal"] = 0
        prev_rsi = df["rsi"].shift(1)

        buy = (prev_rsi < oversold) & (df["rsi"] >= oversold)
        sell = (prev_rsi > overbought) & (df["rsi"] <= overbought)
        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df
