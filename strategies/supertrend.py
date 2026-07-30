# strategies/supertrend.py — Supertrend Strategy
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy

class SupertrendStrategy(BaseStrategy):
    CONFIG_KEY = "Supertrend"
    @property
    def name(self): return "supertrend"
    def prepare(self, df):
        p=int(self.get_param("period",10)); m=float(self.get_param("multiplier",3.0))
        h,l,c=self._series(df,"high"),self._series(df,"low"),self._series(df,"close")
        pc=c.shift(1)
        tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
        atr=tr.ewm(alpha=1/p,adjust=False).mean()
        hl2=(h+l)/2
        bu=hl2+m*atr; bl=hl2-m*atr
        fu=bu.copy(); fl=bl.copy()
        st=pd.Series(np.nan,index=c.index); dr=pd.Series(1,index=c.index)
        for i in range(1,len(c)):
            fu.iloc[i]=bu.iloc[i] if bu.iloc[i]<fu.iloc[i-1] or c.iloc[i-1]>fu.iloc[i-1] else fu.iloc[i-1]
            fl.iloc[i]=bl.iloc[i] if bl.iloc[i]>fl.iloc[i-1] or c.iloc[i-1]<fl.iloc[i-1] else fl.iloc[i-1]
            if pd.isna(st.iloc[i-1]): dr.iloc[i]=1
            elif st.iloc[i-1]==fu.iloc[i-1]: dr.iloc[i]=1 if c.iloc[i]>fu.iloc[i] else -1
            else: dr.iloc[i]=-1 if c.iloc[i]<fl.iloc[i] else 1
            st.iloc[i]=fl.iloc[i] if dr.iloc[i]==1 else fu.iloc[i]
        df["supertrend"]=st; df["st_dir"]=dr
        return df
    def generate_signals(self, df):
        df["signal"]=0; pd_=df["st_dir"].shift(1)
        df.loc[(pd_==-1)&(df["st_dir"]==1),"signal"]=1
        df.loc[(pd_==1)&(df["st_dir"]==-1),"signal"]=-1
        return df
