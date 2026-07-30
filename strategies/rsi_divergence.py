# strategies/rsi_divergence.py — RSI Divergence Strategy
import pandas as pd
import numpy as np
from engine.indicators import rsi as calc_rsi
from strategies.base import BaseStrategy

def _swing_lows(s, lb=5):
    r=pd.Series(False,index=s.index)
    for i in range(lb,len(s)-lb):
        if s.iloc[i]==s.iloc[i-lb:i+lb+1].min(): r.iloc[i]=True
    return r

def _swing_highs(s, lb=5):
    r=pd.Series(False,index=s.index)
    for i in range(lb,len(s)-lb):
        if s.iloc[i]==s.iloc[i-lb:i+lb+1].max(): r.iloc[i]=True
    return r

class RSIDivergenceStrategy(BaseStrategy):
    CONFIG_KEY = "RSIDivergence"
    @property
    def name(self): return "rsi_divergence"
    def prepare(self, df):
        lb=int(self.get_param("swing_lb",5)); c=self._series(df,"close")
        df["divg_rsi"]=calc_rsi(c,14)
        df["sw_low"]=_swing_lows(c,lb); df["sw_high"]=_swing_highs(c,lb)
        df["rsi_low"]=_swing_lows(df["divg_rsi"],lb); df["rsi_high"]=_swing_highs(df["divg_rsi"],lb)
        w=lb*3
        def bull(i):
            if i<w: return False
            cs=c.iloc[i-w:i+1]; rs=df["divg_rsi"].iloc[i-w:i+1]
            m=df["sw_low"].iloc[i-w:i+1]; sw=cs[m]; rw=rs[m]
            if len(sw)<2: return False
            return sw.iloc[-1]<sw.iloc[-2] and rw.iloc[-1]>rw.iloc[-2]
        def bear(i):
            if i<w: return False
            cs=c.iloc[i-w:i+1]; rs=df["divg_rsi"].iloc[i-w:i+1]
            m=df["sw_high"].iloc[i-w:i+1]; sw=cs[m]; rw=rs[m]
            if len(sw)<2: return False
            return sw.iloc[-1]>sw.iloc[-2] and rw.iloc[-1]<rw.iloc[-2]
        df["bull_div"]=pd.Series([bull(i) for i in range(len(df))],index=df.index)
        df["bear_div"]=pd.Series([bear(i) for i in range(len(df))],index=df.index)
        return df
    def generate_signals(self, df):
        df["signal"]=0
        df.loc[df["bull_div"]&(df["divg_rsi"]<55),"signal"]=1
        df.loc[df["bear_div"]&(df["divg_rsi"]>45),"signal"]=-1
        return df
