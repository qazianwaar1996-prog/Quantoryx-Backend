# ai_engine/strategy_selector.py

from typing import Dict, List, Any, Tuple
from ai_engine.confidence_model import ConfidenceModel


class StrategySelector:
    """
    Evaluates individual strategies for a given currency pair and timeframe.
    Identifies the strategy with the highest scoring confidence level.
    """
    def __init__(self, confidence_model: ConfidenceModel = None):
        self.confidence_model = confidence_model if confidence_model is not None else ConfidenceModel()

    def select_best_strategy(
        self,
        current_regime: str,
        wfv_summaries: List[Dict[str, Any]]
    ) -> Tuple[str, Dict[str, Any], float, Dict[str, float]]:
        """
        Evaluates a list of strategy profiles and selects the champion.
        
        Parameters:
            current_regime: The active classified market condition (e.g. "Ranging")
            wfv_summaries: A list of dicts representing historical validation outputs.
                           Format: [
                               {
                                   "strategy": "RSI", 
                                   "avg_oos_sharpe": 1.45, 
                                   "avg_oos_win_rate": 0.58, 
                                   "avg_oos_profit_factor": 1.65, 
                                   "active_params": {...}
                               }, ...
                           ]
                           
        Returns:
            Tuple of:
                - Selected Strategy Name (str)
                - Optimized Parameters (dict)
                - Confidence Score (float)
                - Leaderboard dictionary of all evaluated scores (dict)
        """
        if not wfv_summaries:
            raise ValueError("No walk-forward summaries provided to the strategy selector.")

        leaderboard = {}
        best_strategy = ""
        best_params = {}
        best_score = -1.0

        for item in wfv_summaries:
            strategy_name = item.get("strategy")
            # Pull metrics
            oos_sharpe = float(item.get("avg_oos_sharpe", 0.0))
            oos_win_rate = float(item.get("avg_oos_win_rate", 0.50)) # assume default 50%
            oos_pf = float(item.get("avg_oos_profit_factor", 1.0))
            params = item.get("active_params", {})

            # Compute current active confidence score
            score = self.confidence_model.compute_score(
                strategy_name=strategy_name,
                current_regime=current_regime,
                oos_sharpe=oos_sharpe,
                oos_win_rate=oos_win_rate,
                oos_profit_factor=oos_pf
            )

            leaderboard[strategy_name] = score

            if score > best_score:
                best_score = score
                best_strategy = strategy_name
                best_params = params

        return best_strategy, best_params, best_score, leaderboard
