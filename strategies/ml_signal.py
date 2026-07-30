# strategies/ml_signal.py — LightGBM ML Signal Strategy
import warnings, os, pandas as pd, numpy as np
from engine.indicators import ema, rsi as calc_rsi, macd as calc_macd, bollinger_bands
from strategies.base import BaseStrategy
try:
    import lightgbm as lgb
    from sklearn.model_selection import TimeSeriesSplit
    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False
try:
    import joblib; HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False

FEAT_COLS = ["ret1","ret5","ret10","ret20","rsi","rsi_l1","rsi_l3","macd_h","macd_hs","ema_cross","bb_pos","bb_w","atr_pct","stoch_k","stoch_d","hl_spread"]

def _features(df):
    c=df["close"] if "close" in df.columns else df["Close"]
    h=df["high"] if "high" in df.columns else df["High"]
    l=df["low"] if "low" in df.columns else df["Low"]
    f=pd.DataFrame(index=df.index)
    f["ret1"]=c.pct_change(1); f["ret5"]=c.pct_change(5); f["ret10"]=c.pct_change(10); f["ret20"]=c.pct_change(20)
    f["rsi"]=calc_rsi(c,14); f["rsi_l1"]=f["rsi"].shift(1); f["rsi_l3"]=f["rsi"].shift(3)
    m=calc_macd(c,12,26,9); f["macd_h"]=m["histogram"]; f["macd_hs"]=f["macd_h"].diff()
    f["ema_cross"]=ema(c,9)-ema(c,21); f["ema_cross_s"]=f["ema_cross"].diff()
    bb=bollinger_bands(c,20,2.0); dn=(bb["upper"]-bb["lower"]).replace(0,np.nan)
    f["bb_pos"]=(c-bb["lower"])/dn; f["bb_w"]=dn/bb["middle"].replace(0,np.nan)
    pc=c.shift(1); tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    f["atr_pct"]=tr.ewm(com=13,adjust=False).mean()/c*100
    lo=l.rolling(14).min(); hi=h.rolling(14).max(); sk=100*(c-lo)/(hi-lo+1e-9)
    f["stoch_k"]=sk; f["stoch_d"]=sk.rolling(3).mean()
    f["hl_spread"]=(h-l)/c; f.dropna(inplace=True)
    return f

class MLSignalStrategy(BaseStrategy):
    CONFIG_KEY="MLSignal"
    def __init__(self,params=None):
        super().__init__(params); self._model=None; self._trained=False
    @property
    def name(self): return "ml_signal"
    def train(self,df):
        if not HAS_LGBM:
            warnings.warn("lightgbm not installed. pip install lightgbm scikit-learn"); return {"trained":False}
        feats=_features(df); c=df["close"] if "close" in df.columns else df["Close"]
        tgt=(c.shift(-1)>c).astype(int).reindex(feats.index).dropna()
        X=feats.loc[tgt.index]; y=tgt
        tscv=TimeSeriesSplit(n_splits=int(self.get_param("cv_splits",5)))
        params={"objective":"binary","metric":"binary_logloss","learning_rate":0.05,"num_leaves":31,"min_child_samples":30,"feature_fraction":0.8,"bagging_fraction":0.8,"bagging_freq":5,"verbose":-1}
        accs=[]; model=None
        for tri,vi in tscv.split(X):
            model=lgb.LGBMClassifier(**params,n_estimators=300)
            model.fit(X.iloc[tri],y.iloc[tri],eval_set=[(X.iloc[vi],y.iloc[vi])],callbacks=[lgb.early_stopping(30,verbose=False),lgb.log_evaluation(-1)])
            accs.append((model.predict(X.iloc[vi])==y.iloc[vi]).mean())
        self._model=model; self._trained=True
        mp=self.get_param("model_path",None)
        if mp and HAS_JOBLIB: os.makedirs(os.path.dirname(mp),exist_ok=True); joblib.dump(model,mp)
        return {"trained":True,"mean_cv_acc":round(float(np.mean(accs)),4)}
    def load_model(self,path):
        if not HAS_JOBLIB: raise ImportError("pip install joblib")
        self._model=joblib.load(path); self._trained=True
    def prepare(self,df):
        feats=_features(df)
        for col in FEAT_COLS:
            if col in feats.columns: df[f"ml_{col}"]=feats[col].reindex(df.index)
        return df
    def generate_signals(self,df):
        th=float(self.get_param("threshold",0.62)); df["signal"]=0; df["ml_conf"]=0.0
        if self._trained and self._model and HAS_LGBM:
            cols=[f"ml_{c}" for c in FEAT_COLS if f"ml_{c}" in df.columns]
            X=df[cols].rename(columns={f"ml_{c}":c for c in FEAT_COLS}).dropna()
            if X.empty: return df
            pu=self._model.predict_proba(X)[:,1]
            df.loc[X.index[pu>=th],"signal"]=1
            df.loc[X.index[(1-pu)>=th],"signal"]=-1
            df.loc[X.index,"ml_conf"]=np.maximum(pu,1-pu)
        else:
            if "ml_rsi" in df.columns:
                df.loc[df["ml_rsi"]<35,"signal"]=1; df.loc[df["ml_rsi"]>65,"signal"]=-1
        return df
