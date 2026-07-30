# ============================================================
# strategies/ema_crossover.py — EMA Crossover Strategy
# ============================================================
# Logic:
#   BUY  when the fast EMA crosses ABOVE the slow EMA
#   SELL when the fast EMA crosses BELOW the slow EMA
# ============================================================

import pandas as pd

from engine.indicators import ema
from strategies.base import BaseStrategy


class EMACrossoverStrategy(BaseStrategy):
    """Trend-following dual-EMA crossover."""

    CONFIG_KEY = "EMA"

    @property
    def name(self) -> str:
        return "ema_crossover"

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        fast = int(self.get_param("fast_period", 10))
        slow = int(self.get_param("slow_period", 30))
        close = self._series(df, "close")
        df["ema_fast"] = ema(close, fast)
        df["ema_slow"] = ema(close, slow)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["signal"] = 0
        prev_fast = df["ema_fast"].shift(1)
        prev_slow = df["ema_slow"].shift(1)

        buy = (prev_fast <= prev_slow) & (df["ema_fast"] > df["ema_slow"])
        sell = (prev_fast >= prev_slow) & (df["ema_fast"] < df["ema_slow"])
        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df
