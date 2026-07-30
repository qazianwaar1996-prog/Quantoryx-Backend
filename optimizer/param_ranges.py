# optimizer/param_ranges.py

import itertools
from typing import Dict, List, Any, Iterator

# Define standard search ranges for each strategy.
# These grids can be adjusted depending on resource availability and search depth.

DEFAULT_RANGES = {
    "EMA": {
        "fast_period": list(range(5, 51, 5)),      # [5, 10, 15, ..., 50]
        "slow_period": list(range(20, 201, 20)),   # [20, 40, 60, ..., 200]
    },
    "RSI": {
        "period": list(range(7, 22, 2)),           # [7, 9, 11, ..., 21]
        "oversold": list(range(20, 36, 5)),         # [20, 25, 30, 35]
        "overbought": list(range(65, 81, 5)),        # [65, 70, 75, 80]
    },
    "MACD": {
        "fast_period": list(range(8, 17, 2)),      # [8, 10, 12, 14, 16]
        "slow_period": list(range(20, 33, 3)),      # [20, 23, 26, 29, 32]
        "signal_period": list(range(7, 12, 2)),     # [7, 9, 11]
    },
    "BollingerBands": {
        "period": list(range(10, 31, 5)),          # [10, 15, 20, 25, 30]
        "std_dev": [1.5, 2.0, 2.5],
    },
    "Breakout": {
        "lookback_period": list(range(10, 51, 10)), # [10, 20, 30, 40, 50]
        "breakout_factor": [1.0, 1.01, 1.02],      # multiplier / buffer above channel
    },
    "SupportResistance": {
        "left_bars": list(range(3, 11, 2)),         # [3, 5, 7, 9]
        "right_bars": list(range(3, 11, 2)),        # [3, 5, 7, 9]
        "retest_threshold": [0.001, 0.003, 0.005],  # proximity margin
    },
    "TrendPullback": {
        "trend_period": list(range(50, 201, 50)),   # [50, 100, 150, 200]
        "pullback_rsi_period": [9, 14],
        "pullback_rsi_trigger": [30, 35, 40],       # Entry trigger levels
    }
}


def generate_combinations(strategy_name: str, custom_ranges: Dict[str, List[Any]] = None) -> List[Dict[str, Any]]:
    """
    Generates an array of strategy parameter combinations filtering out mathematically invalid sets.
    """
    ranges = custom_ranges if custom_ranges is not None else DEFAULT_RANGES.get(strategy_name)
    
    if not ranges:
        raise ValueError(f"Strategy '{strategy_name}' ranges are not defined.")

    # Get keys and values in order
    keys = list(ranges.keys())
    values = list(ranges.values())
    
    combinations = []
    # Cartesian product of parameter grids
    for combo in itertools.product(*values):
        param_dict = dict(zip(keys, combo))
        
        # Apply boundary rules and business constraints
        if not _is_valid_combination(strategy_name, param_dict):
            continue
            
        combinations.append(param_dict)
        
    return combinations


def _is_valid_combination(strategy_name: str, params: Dict[str, Any]) -> bool:
    """
    Filters out logically invalid parameter subsets before execution.
    """
    if strategy_name == "EMA":
        # Fast period must be shorter than slow period
        if params["fast_period"] >= params["slow_period"]:
            return False
            
    elif strategy_name == "MACD":
        # Fast period must be shorter than slow period
        if params["fast_period"] >= params["slow_period"]:
            return False
            
    elif strategy_name == "RSI":
        # Oversold must be lower than overbought
        if params["oversold"] >= params["overbought"]:
            return False
            
    return True
