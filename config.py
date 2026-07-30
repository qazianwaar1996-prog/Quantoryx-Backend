# config.py
"""
Quantoryx — central configuration module.

This is the single source of truth for system-wide constants: branding,
default account/transaction settings, global risk limits, per-strategy
default parameters, market reference data, and canonical output locations.

All tunable values live here so that individual modules never hard-code
magic numbers. Import the constants you need directly, e.g.::

    from config import DEFAULT_CAPITAL, RISK_LIMITS, STRATEGY_DEFAULTS
"""

import os
from typing import Any, Dict, List

from utils.path_manager import PathManager

# Initialize the standardized workspace folders on import
PathManager.initialize_workspace()

# =====================================================================
# SYSTEM BRANDING & VERSION CONTROL
# =====================================================================
SYSTEM_NAME = "Quantoryx"
VERSION = "3.0.0"

# =====================================================================
# DEFAULT TRANSACTION & ACCOUNT ALLOCATIONS
# =====================================================================
DEFAULT_CAPITAL = 100000.0
DEFAULT_LEVERAGE = 30.0
DEFAULT_SPREAD = 0.0002
DEFAULT_CONFIDENCE_THRESHOLD = 65.0

# =====================================================================
# GLOBAL RISK MANAGEMENT GATEWAY LIMITS
# =====================================================================
RISK_LIMITS = {
    "risk_per_trade_pct": 1.0,           # Standard 1.0% capital risk per trade
    "max_daily_loss_pct": 3.0,           # Daily loss tolerance limit
    "max_total_drawdown_pct": 10.0,      # Max cumulative drawdown before pause
    "max_concurrent_trades": 3,          # Peak concurrent trade ceiling
    "max_exposure_per_pair_pct": 15.0,   # Absolute single-asset exposure ceiling
    "default_rr_ratio": 2.5              # Target Risk-to-Reward ratio
}

# =====================================================================
# MARKET REFERENCE DATA
# ---------------------------------------------------------------------
# Instruments and timeframes the engine recognizes, plus per-pair pip
# metadata used for optional forex-style price/pip conversions. These are
# centralized here so datasets and strategies share one canonical source.
# =====================================================================
SUPPORTED_PAIRS: List[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
]

SUPPORTED_TIMEFRAMES: List[str] = ["M15", "M30", "1H", "H1", "4H", "H4", "1D", "D1"]

# Pip size per pair (JPY pairs quote to 3 decimals, others to 5).
PIP_SIZE: Dict[str, float] = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
    "NZDUSD": 0.0001, "USDCHF": 0.0001, "USDCAD": 0.0001,
    "USDJPY": 0.01,
}
DEFAULT_PIP_SIZE = 0.0001

# =====================================================================
# CANONICAL WORKSPACE DIRECTORIES
# ---------------------------------------------------------------------
# Thin, human-readable aliases over PathManager's directory registry so
# callers can reference well-known locations without duplicating strings.
# =====================================================================
DATA_DIR = PathManager.DIRECTORIES["data"]
OUTPUT_DIR = PathManager.DIRECTORIES["output"]
REPORTS_DIR = PathManager.DIRECTORIES["reports"]
LOGS_DIR = PathManager.DIRECTORIES["logs"]

# =====================================================================
# DEFAULT STRATEGY PARAMETERS
# =====================================================================
STRATEGY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "EMA": {
        "fast_period": 10,
        "slow_period": 30
    },
    "RSI": {
        "period": 14,
        "oversold": 30.0,
        "overbought": 70.0
    },
    "MACD": {
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9
    },
    "BollingerBands": {
        "period": 20,
        "std_dev": 2.0
    },
    "Breakout": {
        "lookback_period": 20,
        "breakout_factor": 1.01
    },
    "SupportResistance": {
        "left_bars": 5,
        "right_bars": 5,
        "retest_threshold": 0.002
    },
    "TrendPullback": {
        "trend_period": 100,
        "pullback_rsi_period": 14,
        "pullback_rsi_trigger": 35.0
    }
}


def get_strategy_config(strategy_name: str, custom_params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Safely retrieves the parameter configuration for a target strategy.
    Overlays any custom user parameters on top of the system defaults.
    """
    normalized_name = strategy_name.upper().replace("_", "").replace(" ", "")
    
    # Map normalized names back to default keys
    key_mapping = {
        "EMA": "EMA",
        "RSI": "RSI",
        "MACD": "MACD",
        "BOLLINGERBANDS": "BollingerBands",
        "BB": "BollingerBands",
        "BREAKOUT": "Breakout",
        "SUPPORTRESISTANCE": "SupportResistance",
        "SR": "SupportResistance",
        "TRENDPULLBACK": "TrendPullback"
    }
    
    mapped_key = key_mapping.get(normalized_name)
    if not mapped_key:
        raise ValueError(f"Strategy '{strategy_name}' is not classified under standard Quantoryx defaults.")
        
    defaults = STRATEGY_DEFAULTS[mapped_key].copy()
    
    if custom_params:
        for k, v in custom_params.items():
            if k in defaults:
                # Retain structural data types (e.g., cast string numbers to expected int or float)
                expected_type = type(defaults[k])
                try:
                    defaults[k] = expected_type(v)
                except (ValueError, TypeError):
                    defaults[k] = v
            else:
                defaults[k] = v
                
    return defaults

# ── God-Level Strategy Defaults ───────────────────────────────────────────────
if hasattr(STRATEGY_DEFAULTS, 'update'):
    STRATEGY_DEFAULTS.update({
        "Stochastic":{"k_period":14,"d_period":3,"oversold":20.0,"overbought":80.0},
        "Ichimoku":{"tenkan":9,"kijun":26,"senkou_b":52,"displacement":26},
        "Momentum":{"roc_period":20,"ema_period":50,"threshold":0.3},
        "MeanReversion":{"period":50,"entry_z":2.0},
        "VolatilityBreakout":{"ema_period":20,"atr_period":14,"kc_mult":1.5},
        "VWAPReversion":{"period":20,"dev_threshold":0.15},
        "TripleEMA":{"fast":8,"medium":21,"slow":55},
        "RSIDivergence":{"swing_lb":5},
        "Supertrend":{"period":10,"multiplier":3.0},
        "MLSignal":{"threshold":0.62,"cv_splits":5},
        "RegimeAdaptive":{},
    })
