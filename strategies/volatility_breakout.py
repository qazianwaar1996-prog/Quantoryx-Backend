# strategies/volatility_breakout.py — Keltner + Bollinger Squeeze
import pandas as pd
import numpy as np
from engine.indicators import ema, bollinger_bands
from strategies.base import BaseStrategy

class VolatilityBreakoutStrategy(BaseStrategy):
    CONFIG_KEY = "VolatilityBreakout"
    @property
    def name(self): return "volatility_breakout"
    def prepare(self, df):
        ep=int(self.get_param("ema_period",20)); ap=int(self.get_param("atr_period",14))
        m=float(self.get_param("kc_mult",1.5))
        c,h,l=self._series(df,"close"),self._series(df,"high"),self._series(df,"low")
        mid=ema(c,ep); pc=c.shift(1)
        tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
        atr=tr.ewm(alpha=1/ap,adjust=False).mean()
        df["kc_upper"]=mid+m*atr; df["kc_lower"]=mid-m*atr; df["kc_mid"]=mid
        bb=bollinger_bands(c,20,2.0)
        df["bb_upper"]=bb["upper"]; df["bb_lower"]=bb["lower"]
        df["in_squeeze"]=(df["bb_upper"]<df["kc_upper"])&(df["bb_lower"]>df["kc_lower"])
        df["sq_mom"]=c-mid
        return df
    def generate_signals(self, df):
        c=self._series(df,"close"); pc=c.shift(1); df["signal"]=0
        df.loc[(c>df["kc_upper"])&(pc<=df["kc_upper"].shift(1))&(df["sq_mom"]>df["sq_mom"].shift(1)),"signal"]=1
        df.loc[(c<df["kc_lower"])&(pc>=df["kc_lower"].shift(1))&(df["sq_mom"]<df["sq_mom"].shift(1)),"signal"]=-1
        return df
