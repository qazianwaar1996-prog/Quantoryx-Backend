# strategies/mean_reversion.py — Z-Score Mean Reversion
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy

class MeanReversionStrategy(BaseStrategy):
    CONFIG_KEY = "MeanReversion"
    @property
    def name(self): return "mean_reversion"
    def prepare(self, df):
        p=int(self.get_param("period",50)); c=self._series(df,"close")
        df["mr_mean"]=c.rolling(p).mean()
        df["mr_std"]=c.rolling(p).std()
        df["mr_zscore"]=(c-df["mr_mean"])/df["mr_std"].replace(0,np.nan)
        return df
    def generate_signals(self, df):
        ez=float(self.get_param("entry_z",2.0)); df["signal"]=0
        df.loc[df["mr_zscore"]<-ez,"signal"]=1
        df.loc[df["mr_zscore"]>ez,"signal"]=-1
        return df
