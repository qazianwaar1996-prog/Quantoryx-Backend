# strategies/momentum.py — Multi-Factor Momentum Strategy
import pandas as pd
import numpy as np
from engine.indicators import ema, rsi as calc_rsi
from strategies.base import BaseStrategy

class MomentumStrategy(BaseStrategy):
    CONFIG_KEY = "Momentum"
    @property
    def name(self): return "momentum"
    def prepare(self, df):
        rp=int(self.get_param("roc_period",20)); ep=int(self.get_param("ema_period",50))
        c=self._series(df,"close")
        df["mom_roc"]=c.pct_change(rp)*100
        df["mom_roc_f"]=c.pct_change(max(1,rp//2))*100
        df["mom_rsi"]=calc_rsi(c,14)
        df["mom_ema"]=ema(c,ep)
        df["mom_slope"]=df["mom_ema"].pct_change(5)*100
        df["mom_score"]=df["mom_roc"].fillna(0)*0.6+df["mom_roc_f"].fillna(0)*0.4
        return df
    def generate_signals(self, df):
        th=float(self.get_param("threshold",0.3)); c=self._series(df,"close")
        df["signal"]=0
        df.loc[(df["mom_score"]>th)&(df["mom_rsi"]>50)&(c>df["mom_ema"])&(df["mom_slope"]>0),"signal"]=1
        df.loc[(df["mom_score"]<-th)&(df["mom_rsi"]<50)&(c<df["mom_ema"])&(df["mom_slope"]<0),"signal"]=-1
        return df
