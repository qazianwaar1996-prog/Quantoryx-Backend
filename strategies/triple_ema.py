# strategies/triple_ema.py — Triple EMA Stack with Pullback Entries
import pandas as pd
import numpy as np
from engine.indicators import ema
from strategies.base import BaseStrategy

class TripleEMAStrategy(BaseStrategy):
    CONFIG_KEY = "TripleEMA"
    @property
    def name(self): return "triple_ema"
    def prepare(self, df):
        f=int(self.get_param("fast",8)); m=int(self.get_param("medium",21)); s=int(self.get_param("slow",55))
        c=self._series(df,"close")
        df["tema_f"]=ema(c,f); df["tema_m"]=ema(c,m); df["tema_s"]=ema(c,s)
        bull=(df["tema_f"]>df["tema_m"])&(df["tema_m"]>df["tema_s"])
        bear=(df["tema_f"]<df["tema_m"])&(df["tema_m"]<df["tema_s"])
        df["tema_stack"]=0
        df.loc[bull,"tema_stack"]=1; df.loc[bear,"tema_stack"]=-1
        df["tema_dist"]=(c-df["tema_m"])/df["tema_m"]*100
        return df
    def generate_signals(self, df):
        rt=float(self.get_param("retest_pct",0.1)); df["signal"]=0
        c=self._series(df,"close"); pd_=df["tema_dist"].shift(1)
        df.loc[(df["tema_stack"]==1)&(pd_.abs()<=rt)&(c>df["tema_m"]),"signal"]=1
        df.loc[(df["tema_stack"]==-1)&(pd_.abs()<=rt)&(c<df["tema_m"]),"signal"]=-1
        return df
