# strategies/__init__.py — Complete Quantoryx Strategy Registry

from strategies.ema_crossover       import EMACrossoverStrategy
from strategies.rsi                 import RSIStrategy
from strategies.macd                import MACDStrategy
from strategies.bollinger           import BollingerStrategy
from strategies.breakout            import BreakoutStrategy
from strategies.support_resistance  import SupportResistanceStrategy
from strategies.trend_pullback      import TrendPullbackStrategy
from strategies.stochastic          import StochasticStrategy
from strategies.ichimoku            import IchimokuStrategy
from strategies.momentum            import MomentumStrategy
from strategies.mean_reversion      import MeanReversionStrategy
from strategies.volatility_breakout import VolatilityBreakoutStrategy
from strategies.vwap_reversion      import VWAPReversionStrategy
from strategies.triple_ema          import TripleEMAStrategy
from strategies.rsi_divergence      import RSIDivergenceStrategy
from strategies.supertrend          import SupertrendStrategy
from strategies.ml_signal           import MLSignalStrategy
from strategies.regime_adaptive     import RegimeAdaptiveStrategy

STRATEGY_REGISTRY = {
    "ema_crossover":EMACrossoverStrategy,"rsi":RSIStrategy,"macd":MACDStrategy,
    "bollinger":BollingerStrategy,"breakout":BreakoutStrategy,
    "support_resistance":SupportResistanceStrategy,"trend_pullback":TrendPullbackStrategy,
    "stochastic":StochasticStrategy,"ichimoku":IchimokuStrategy,"momentum":MomentumStrategy,
    "mean_reversion":MeanReversionStrategy,"volatility_breakout":VolatilityBreakoutStrategy,
    "vwap_reversion":VWAPReversionStrategy,"triple_ema":TripleEMAStrategy,
    "rsi_divergence":RSIDivergenceStrategy,"supertrend":SupertrendStrategy,
    "ml_signal":MLSignalStrategy,"regime_adaptive":RegimeAdaptiveStrategy,
}

CATEGORIES = {
    "Trend Following":["ema_crossover","triple_ema","supertrend","ichimoku","trend_pullback","momentum"],
    "Mean Reversion":["rsi","bollinger","stochastic","mean_reversion","vwap_reversion","rsi_divergence"],
    "Breakout":["breakout","volatility_breakout","support_resistance"],
    "Momentum":["macd","momentum","rsi_divergence"],
    "AI / Machine Learning":["ml_signal"],
    "Adaptive / Meta":["regime_adaptive"],
}

REGIME_FIT = {
    "ema_crossover":["Trending"],"rsi":["Ranging"],"macd":["Trending","Moderate Trend"],
    "bollinger":["Ranging","Low Volatility"],"breakout":["High Volatility"],
    "support_resistance":["Ranging"],"trend_pullback":["Trending"],
    "stochastic":["Ranging"],"ichimoku":["Trending","Low Volatility"],
    "momentum":["Trending"],"mean_reversion":["Ranging"],
    "volatility_breakout":["High Volatility"],"vwap_reversion":["Ranging","Moderate Trend"],
    "triple_ema":["Trending"],"rsi_divergence":["Ranging","Moderate Trend"],
    "supertrend":["Trending","High Volatility"],"ml_signal":["All"],"regime_adaptive":["All"],
}

ALIAS_MAP = {
    "EMA":"ema_crossover","EMACROSSOVER":"ema_crossover","RSI":"rsi","MACD":"macd",
    "BOLLINGER":"bollinger","BB":"bollinger","BREAKOUT":"breakout",
    "SR":"support_resistance","SUPPORTRESISTANCE":"support_resistance",
    "TRENDPULLBACK":"trend_pullback","STOCHASTIC":"stochastic","STOCH":"stochastic",
    "ICHIMOKU":"ichimoku","CLOUD":"ichimoku","MOMENTUM":"momentum","MOM":"momentum",
    "MEANREVERSION":"mean_reversion","MR":"mean_reversion","ZSCORE":"mean_reversion",
    "VOLATILITYBREAKOUT":"volatility_breakout","KELTNER":"volatility_breakout",
    "VWAP":"vwap_reversion","VWAPREVERSION":"vwap_reversion",
    "TRIPLEEMA":"triple_ema","TEMA":"triple_ema","3EMA":"triple_ema",
    "RSIDIVERGENCE":"rsi_divergence","DIVERGENCE":"rsi_divergence",
    "SUPERTREND":"supertrend","ST":"supertrend",
    "ML":"ml_signal","MLSIGNAL":"ml_signal","AI":"ml_signal",
    "ADAPTIVE":"regime_adaptive","REGIMEADAPTIVE":"regime_adaptive","AUTO":"regime_adaptive",
}

def get_strategy(name:str, params:dict=None):
    key=ALIAS_MAP.get(name.upper(), name.lower())
    if key not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(STRATEGY_REGISTRY)}")
    return STRATEGY_REGISTRY[key](params=params)

def get_strategy_metadata():
    return {n:{"class":cls.__name__,"category":next((c for c,s in CATEGORIES.items() if n in s),"Other"),"regime_fit":REGIME_FIT.get(n,["All"]),"config_key":cls.CONFIG_KEY} for n,cls in STRATEGY_REGISTRY.items()}

def strategies_for_regime(regime:str):
    return [n for n,rs in REGIME_FIT.items() if regime in rs or "All" in rs]
