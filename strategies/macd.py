# ============================================================
# strategies/macd.py — MACD Signal-Line Crossover Strategy
# ============================================================
# Logic:
#   BUY  when the MACD line crosses ABOVE the signal line
#   SELL when the MACD line crosses BELOW the signal line
# ============================================================

import pandas as pd

from engine.indicators import macd as calc_macd
from strategies.base import BaseStrategy


class MACDStrategy(BaseStrategy):
    """Momentum MACD crossover."""

    CONFIG_KEY = "MACD"

    @property
    def name(self) -> str:
        return "macd"

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        fast = int(self.get_param("fast_period", 12))
        slow = int(self.get_param("slow_period", 26))
        signal = int(self.get_param("signal_period", 9))

        macd_df = calc_macd(self._series(df, "close"), fast, slow, signal)
        df["macd"] = macd_df["macd"]
        df["macd_sig"] = macd_df["signal"]
        df["macd_hist"] = macd_df["histogram"]
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["signal"] = 0
        prev_macd = df["macd"].shift(1)
        prev_sig = df["macd_sig"].shift(1)

        buy = (prev_macd <= prev_sig) & (df["macd"] > df["macd_sig"])
        sell = (prev_macd >= prev_sig) & (df["macd"] < df["macd_sig"])
        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df
