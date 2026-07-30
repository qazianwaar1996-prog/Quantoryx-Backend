# ============================================================
# strategies/bollinger.py — Bollinger Bands Mean-Reversion Strategy
# ============================================================
# Logic:
#   BUY  when price closes BELOW the lower band (mean reversion up)
#   SELL when price closes ABOVE the upper band (mean reversion down)
# ============================================================

import pandas as pd

from engine.indicators import bollinger_bands
from strategies.base import BaseStrategy


class BollingerStrategy(BaseStrategy):
    """Range/reversion Bollinger Bands strategy."""

    CONFIG_KEY = "BollingerBands"

    @property
    def name(self) -> str:
        return "bollinger"

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        period = int(self.get_param("period", 20))
        std_dev = float(self.get_param("std_dev", 2.0))

        bb = bollinger_bands(self._series(df, "close"), period, std_dev)
        df["bb_upper"] = bb["upper"]
        df["bb_middle"] = bb["middle"]
        df["bb_lower"] = bb["lower"]
        # Bandwidth (squeeze detection) — guard against a zero mid-band.
        df["bb_bandwidth"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"].replace(0.0, pd.NA)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        close = self._series(df, "close")
        df["signal"] = 0

        buy = close < df["bb_lower"]
        sell = close > df["bb_upper"]
        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df
