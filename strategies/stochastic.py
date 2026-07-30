# strategies/stochastic.py — Stochastic Oscillator Strategy
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy

class StochasticStrategy(BaseStrategy):
    CONFIG_KEY = "Stochastic"
    @property
    def name(self): return "stochastic"
    def prepare(self, df):
        k = int(self.get_param("k_period", 14))
        d = int(self.get_param("d_period", 3))
        h, l, c = self._series(df,"high"), self._series(df,"low"), self._series(df,"close")
        lo = l.rolling(k).min(); hi = h.rolling(k).max()
        df["stoch_k"] = 100*(c-lo)/(hi-lo+1e-9)
        df["stoch_d"] = df["stoch_k"].rolling(d).mean()
        return df
    def generate_signals(self, df):
        ob = float(self.get_param("overbought", 80))
        os_ = float(self.get_param("oversold", 20))
        df["signal"] = 0
        pk, pd_ = df["stoch_k"].shift(1), df["stoch_d"].shift(1)
        df.loc[(pk<=pd_)&(df["stoch_k"]>df["stoch_d"])&(df["stoch_k"]<os_),"signal"]=1
        df.loc[(pk>=pd_)&(df["stoch_k"]<df["stoch_d"])&(df["stoch_k"]>ob),"signal"]=-1
        return df
