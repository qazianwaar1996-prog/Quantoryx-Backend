# ============================================================
# strategies/support_resistance.py — Support & Resistance Strategy
# ============================================================
# Logic:
#   BUY  when price retests a SUPPORT zone (recent swing low) and holds
#   SELL when price retests a RESISTANCE zone (recent swing high) and fails
# ============================================================

import pandas as pd

from engine.indicators import rolling_high, rolling_low
from strategies.base import BaseStrategy


class SupportResistanceStrategy(BaseStrategy):
    """Level-retest reversion using rolling swing highs/lows."""

    CONFIG_KEY = "SupportResistance"

    @property
    def name(self) -> str:
        return "support_resistance"

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        # ``left_bars``/``right_bars`` bound the swing window; use the widest.
        left = int(self.get_param("left_bars", 5))
        right = int(self.get_param("right_bars", 5))
        lookback = max(2, left + right)
        df["sr_resistance"] = rolling_high(self._series(df, "high"), lookback).shift(1)
        df["sr_support"] = rolling_low(self._series(df, "low"), lookback).shift(1)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        threshold = float(self.get_param("retest_threshold", 0.002))
        close = self._series(df, "close")
        low = self._series(df, "low")
        high = self._series(df, "high")
        df["signal"] = 0

        support_zone = df["sr_support"] * (1.0 + threshold)
        resistance_zone = df["sr_resistance"] * (1.0 - threshold)

        # Dip into support then close back above it → BUY.
        buy = (low <= support_zone) & (close > df["sr_support"])
        # Poke into resistance then close back below it → SELL.
        sell = (high >= resistance_zone) & (close < df["sr_resistance"])
        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df
