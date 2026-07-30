# strategies/vwap_reversion.py — VWAP Reversion Strategy
import pandas as pd
import numpy as np
from engine.indicators import rsi as calc_rsi
from strategies.base import BaseStrategy

class VWAPReversionStrategy(BaseStrategy):
    CONFIG_KEY = "VWAPReversion"
    @property
    def name(self): return "vwap_reversion"
    def prepare(self, df):
        p=int(self.get_param("period",20)); c=self._series(df,"close")
        if "volume" in df.columns and df["volume"].sum()>0:
            vol=df["volume"].replace(0,np.nan).ffill().fillna(1.0)
        else:
            h,l=self._series(df,"high"),self._series(df,"low")
            vol=(h-l).replace(0,np.nan).fillna(c*0.001)
        df["vwap"]=(c*vol).rolling(p).sum()/vol.rolling(p).sum()
        df["vwap_dev"]=(c-df["vwap"])/df["vwap"]*100
        df["vwap_rsi"]=calc_rsi(c,14)
        return df
    def generate_signals(self, df):
        dt=float(self.get_param("dev_threshold",0.15)); df["signal"]=0
        df.loc[(df["vwap_dev"]<-dt)&(df["vwap_rsi"]<40),"signal"]=1
        df.loc[(df["vwap_dev"]>dt)&(df["vwap_rsi"]>60),"signal"]=-1
        return df
