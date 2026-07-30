# learning/tracker.py
"""
Quantoryx — AI Continuous Learning and Parameter Adaptation Module.

Tracks trade outcomes, aggregates strategy performance by regime, calculates 
recalibration metrics, and provides reinforcement-learning state transitions [8].
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.logging_config import get_logger

logger = get_logger("ai.learning")


@dataclass
class LearningTransition:
    """Standardized reinforcement learning state transition (s, a, r, s') [8]."""
    transition_id: str
    
    # State s (Entry Context)
    entry_time: datetime
    entry_regime: str
    entry_volatility: float
    entry_trend_strength: float
    
    # Action a (Strategy & Parameters deployed)
    strategy_name: str
    parameters_json: str
    confidence_score: float
    
    # Reward r (Financial outcome)
    realized_pnl: float
    
    # State s' (Exit Context)
    exit_time: datetime
    exit_regime: str
    exit_volatility: float
    exit_trend_strength: float


class ContinuousLearningTracker:
    """
    Tracks trading performance data to recalibrate confidence models
    and suggest parameter adaptations [8].
    """

    def __init__(self):
        # Map transition_id (str) -> LearningTransition object
        self.transitions: Dict[str, LearningTransition] = {}
        
        # Performance matrix cache
        self.regime_performance: Dict[str, Dict[str, List[float]]] = {} # regime -> {strategy: [pnls]}

    def record_trade_outcome(self, transition: LearningTransition):
        """Registers a completed transaction as an RL state transition [8]."""
        self.transitions[transition.transition_id] = transition
        
        # Update regime performance cache
        regime = transition.entry_regime
        strategy = transition.strategy_name.upper()
        
        if regime not in self.regime_performance:
            self.regime_performance[regime] = {}
        if strategy not in self.regime_performance[regime]:
            self.regime_performance[regime][strategy] = []
            
        self.regime_performance[regime][strategy].append(transition.realized_pnl)
        
        logger.info(
            "AI Learning: Outcome recorded. Transition %s | Strategy: %s | Regime: %s | PnL: %s",
            transition.transition_id, strategy, regime, round(transition.realized_pnl, 2)
        )

    # =====================================================================
    # CONFIDENCE MODEL RECALIBRATION
    # =====================================================================

    def calculate_confidence_recalibration_factor(self, strategy_name: str) -> float:
        """
        Calculates a recalibration factor (0.10 to 2.0) to adjust confidence scores.
        If a strategy's high-confidence setups frequently lose, this factor decreases,
        scaling down future confidence ratings for that model.
        """
        target_strategy = strategy_name.upper()
        matching_transitions = [
            t for t in self.transitions.values() if t.strategy_name.upper() == target_strategy
        ]
        
        if len(matching_transitions) < 5:
            # Sane baseline multiplier until we gather enough sample data
            return 1.0

        high_conf_wins = 0
        high_conf_total = 0

        for t in matching_transitions:
            # Evaluate transactions placed with high predicted confidence (>= 70)
            if t.confidence_score >= 70.0:
                high_conf_total += 1
                if t.realized_pnl > 0:
                    high_conf_wins += 1

        if high_conf_total == 0:
            return 1.0

        actual_win_rate = high_conf_wins / high_conf_total
        # Recalibration multiplier = Actual Win Rate / Expected Benchmark (e.g. 60%)
        recalibration_factor = actual_win_rate / 0.60
        
        # Clamp between 0.20 and 1.50 to prevent wild deviations
        return max(0.20, min(1.50, float(recalibration_factor)))

    # =====================================================================
    # REGIME ADAPTIVE PARAMETER SUGGESTIONS
    # =====================================================================

    def suggest_adaptive_parameters(self, strategy_name: str, current_regime: str) -> Optional[Dict[str, Any]]:
        """
        Scans historical transitions to identify and suggest the parameter combination
        that generated the highest net profit in the specified market regime [8].
        """
        target_strategy = strategy_name.upper()
        
        matching_runs = [
            t for t in self.transitions.values() 
            if t.strategy_name.upper() == target_strategy and t.entry_regime == current_regime
        ]

        if not matching_runs:
            logger.debug("No historical adaptions logged yet for %s under %s.", target_strategy, current_regime)
            return None

        # Aggregate P/L by parameter string
        param_performance: Dict[str, float] = {}
        for run in matching_runs:
            param_performance[run.parameters_json] = param_performance.get(run.parameters_json, 0.0) + run.realized_pnl

        # Find best parameter combination
        best_param_str = max(param_performance, key=param_performance.get)
        
        try:
            import ast
            best_params = ast.literal_eval(best_param_str)
            logger.info("AI Learning: Suggested parameters for %s under %s: %s", target_strategy, current_regime, best_params)
            return best_params
        except Exception as e:
            logger.error("Failed to parse suggested parameter configurations: %s", str(e))
            return None

    # =====================================================================
    # SYSTEM STATE AND BEHAVIOR MONITORS
    # =====================================================================

    def get_strategy_performance_by_regime(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Compiles a matrix detailing performance statistics grouped by strategy and regime [4].
        """
        report: Dict[str, Dict[str, Dict[str, float]]] = {}

        for regime, strategies in self.regime_performance.items():
            report[regime] = {}
            for strategy, pnls in strategies.items():
                pnl_arr = np.array(pnls)
                wins = pnl_arr[pnl_arr > 0]
                losses = pnl_arr[pnl_arr < 0]
                
                win_rate = len(wins) / len(pnl_arr) if len(pnl_arr) > 0 else 0.0
                gross_profit = float(np.sum(wins))
                gross_loss = float(abs(np.sum(losses)))
                profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

                report[regime][strategy] = {
                    "net_profit": float(np.sum(pnl_arr)),
                    "trade_count": float(len(pnl_arr)),
                    "win_rate": float(win_rate),
                    "profit_factor": float(profit_factor)
                }

        return report
