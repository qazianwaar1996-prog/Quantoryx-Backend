# strategies/ichimoku.py — Ichimoku Cloud Strategy
import pandas as pd
from strategies.base import BaseStrategy

def _mid(h,l,p): return (h.rolling(p).max()+l.rolling(p).min())/2

class IchimokuStrategy(BaseStrategy):
    CONFIG_KEY = "Ichimoku"
    @property
    def name(self): return "ichimoku"
    def prepare(self, df):
        t=int(self.get_param("tenkan",9)); k=int(self.get_param("kijun",26))
        sb=int(self.get_param("senkou_b",52)); d=int(self.get_param("displacement",26))
        h,l,c=self._series(df,"high"),self._series(df,"low"),self._series(df,"close")
        ten=_mid(h,l,t); kij=_mid(h,l,k)
        df["ichi_tenkan"]=ten; df["ichi_kijun"]=kij
        df["ichi_sa"]=((ten+kij)/2).shift(d); df["ichi_sb"]=_mid(h,l,sb).shift(d)
        df["cloud_top"]=df[["ichi_sa","ichi_sb"]].max(axis=1)
        df["cloud_bot"]=df[["ichi_sa","ichi_sb"]].min(axis=1)
        return df
    def generate_signals(self, df):
        c=self._series(df,"close"); df["signal"]=0
        pc=c.shift(1)
        buy=(c>df["cloud_top"])&(pc<=df["cloud_top"].shift(1))&(df["ichi_tenkan"]>df["ichi_kijun"])
        sell=(c<df["cloud_bot"])&(pc>=df["cloud_bot"].shift(1))&(df["ichi_tenkan"]<df["ichi_kijun"])
        df.loc[buy,"signal"]=1; df.loc[sell,"signal"]=-1
        return df
