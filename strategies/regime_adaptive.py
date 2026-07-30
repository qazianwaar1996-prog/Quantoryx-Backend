# strategies/regime_adaptive.py — Regime-Adaptive Meta Strategy
import pandas as pd
from strategies.base import BaseStrategy

REGIME_MAP = {
    "Trending Bullish":"triple_ema","Trending Bearish":"triple_ema","Trending":"triple_ema",
    "Ranging":"mean_reversion","High Volatility":"volatility_breakout",
    "Low Volatility":"ichimoku","Moderate Trend":"macd","Normal/Quiet":"macd","Unknown":"macd",
}

class RegimeAdaptiveStrategy(BaseStrategy):
    CONFIG_KEY="RegimeAdaptive"
    def __init__(self,params=None):
        super().__init__(params); self._subs={}
    @property
    def name(self): return "regime_adaptive"
    def _get_sub(self,name):
        if name not in self._subs:
            from strategies import get_strategy
            self._subs[name]=get_strategy(name,self.params)
        return self._subs[name]
    def prepare(self,df):
        if "market_regime" not in df.columns:
            try:
                from market_regime.detector import MarketRegimeDetector
                df=MarketRegimeDetector().classify_regimes(df)
            except: df["market_regime"]="Unknown"
        for sn in set(REGIME_MAP.values()):
            try: df=self._get_sub(sn).prepare(df)
            except: pass
        return df
    def generate_signals(self,df):
        df["signal"]=0; df["active_strategy"]="macd"
        for regime,sname in REGIME_MAP.items():
            mask=df.get("market_regime",pd.Series("Unknown",index=df.index))==regime
            if not mask.any(): continue
            try:
                sub=self._get_sub(sname); sub_df=sub.generate_signals(df.copy())
                df.loc[mask,"signal"]=sub_df.loc[mask,"signal"]
                df.loc[mask,"active_strategy"]=sname
            except: pass
        return df
