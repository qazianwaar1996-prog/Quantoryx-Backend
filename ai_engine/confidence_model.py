# ai_engine/confidence_model.py

import numpy as np
from typing import Dict, Any


class ConfidenceModel:
    """
    Computes a quantitative confidence score (0 to 100) for a strategy 
    by combining historical Out-of-Sample metrics with current market regime alignments.
    """
    def __init__(self):
        # Regime-to-Strategy compatibility matrices
        # Values dictate the structural alignment offset (positive or negative)
        self.regime_matrix = {
            "Trending": {
                "EMA": 25.0,
                "MACD": 20.0,
                "TRENDPULLBACK": 30.0,
                "BREAKOUT": 25.0,
                "RSI": -15.0,
                "BOLLINGERBANDS": -20.0,
                "SUPPORTRESISTANCE": -10.0
            },
            "Trending Bullish": {
                "EMA": 30.0,
                "MACD": 25.0,
                "TRENDPULLBACK": 35.0,
                "BREAKOUT": 25.0,
                "RSI": -10.0,
                "BOLLINGERBANDS": -15.0,
                "SUPPORTRESISTANCE": -10.0
            },
            "Trending Bearish": {
                "EMA": 30.0,
                "MACD": 25.0,
                "TRENDPULLBACK": 35.0,
                "BREAKOUT": 25.0,
                "RSI": -10.0,
                "BOLLINGERBANDS": -15.0,
                "SUPPORTRESISTANCE": -10.0
            },
            "Ranging": {
                "RSI": 30.0,
                "BOLLINGERBANDS": 30.0,
                "SUPPORTRESISTANCE": 25.0,
                "EMA": -20.0,
                "MACD": -15.0,
                "TRENDPULLBACK": -15.0,
                "BREAKOUT": -10.0
            },
            "High Volatility": {
                "BREAKOUT": 30.0,
                "BOLLINGERBANDS": 10.0,
                "SUPPORTRESISTANCE": -15.0,
                "RSI": -10.0,
                "EMA": 5.0,
                "MACD": 5.0,
                "TRENDPULLBACK": 10.0
            },
            "Low Volatility": {
                "RSI": 15.0,
                "BOLLINGERBANDS": 15.0,
                "SUPPORTRESISTANCE": 10.0,
                "EMA": -10.0,
                "MACD": -10.0,
                "TRENDPULLBACK": -5.0,
                "BREAKOUT": -15.0
            }
        }

    def compute_score(
        self,
        strategy_name: str,
        current_regime: str,
        oos_sharpe: float,
        oos_win_rate: float,
        oos_profit_factor: float
    ) -> float:
        """
        Calculates a deterministic confidence score between 0.0 and 100.0.
        Combines out-of-sample performance consistency (60% weight) with 
        regime-to-strategy structural compatibility (40% weight).
        """
        strategy_key = strategy_name.upper().replace("_", "").replace(" ", "")
        
        # 1. Base Historical Performance Score (Max 100)
        # Normalizes Sharpe Ratio (targets Sharpe of 2.0+ for 50 pts) and Win Rate (targets 65%+ for 50 pts)
        sharpe_score = min(50.0, max(0.0, (oos_sharpe / 2.0) * 50.0))
        win_rate_score = min(50.0, max(0.0, oos_win_rate * 100.0))
        profit_factor_bonus = min(10.0, max(0.0, (oos_profit_factor - 1.0) * 10.0))
        
        base_performance_score = min(100.0, sharpe_score + win_rate_score + profit_factor_bonus)

        # 2. Regime Compatibility Score (Max 100)
        # Starts at a neutral baseline of 50.0 and applies matrix offsets
        regime_bonus = 0.0
        normalized_regime = current_regime
        
        # Match standard or composite regimes
        if current_regime not in self.regime_matrix:
            if "Trending" in current_regime:
                normalized_regime = "Trending"
            elif "Normal" in current_regime or "Moderate" in current_regime:
                normalized_regime = "Low Volatility"
            else:
                normalized_regime = "Low Volatility"  # Conservative fallback

        regime_rules = self.regime_matrix.get(normalized_regime, {})
        regime_bonus = regime_rules.get(strategy_key, 0.0)
        
        regime_score = min(100.0, max(0.0, 50.0 + regime_bonus))

        # 3. Weighted Combination
        final_confidence = (base_performance_score * 0.60) + (regime_score * 0.40)
        
        return round(float(final_confidence), 1)
