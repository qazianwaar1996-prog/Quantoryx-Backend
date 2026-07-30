# ai_engine/decision_engine.py

import os
import csv
from datetime import datetime
from typing import Dict, List, Any

# Core integrations
from ai_engine.confidence_model import ConfidenceModel
from ai_engine.strategy_selector import StrategySelector
from ai_engine.explanation_engine import ExplanationEngine
from utils.path_manager import PathManager


class AIDecisionEngine:
    """
    Orchestrates the AI module. Evaluates candidate strategies, calculates
    confidence scores, generates narrative explanations, and filters out low-confidence setups.
    """
    def __init__(
        self,
        confidence_threshold: float = 60.0,
        risk_level: str = "Medium",
        log_filepath: str = None
    ):
        self.confidence_threshold = confidence_threshold
        self.risk_level = risk_level
        
        # Resolve target log path via PathManager if no specific override is supplied
        if log_filepath is None:
            self.log_filepath = PathManager.resolve_path("logs", "ai_decision_log.csv")
        else:
            self.log_filepath = log_filepath

        # Instantiate sub-components
        self.confidence_model = ConfidenceModel()
        self.selector = StrategySelector(self.confidence_model)
        self.explainer = ExplanationEngine()
        
        # State tracking
        self.decisions_history: List[Dict[str, Any]] = []

    def evaluate_current_state(
        self,
        symbol: str,
        timeframe: str,
        current_regime: str,
        wfv_summaries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Processes candidate summaries and decides whether to run or skip the champion model.
        """
        # 1. Nominate the best strategy using our Confidence Model
        best_strategy, best_params, confidence_score, leaderboard = self.selector.select_best_strategy(
            current_regime=current_regime,
            wfv_summaries=wfv_summaries
        )

        # 2. Apply threshold filter (Skip if confidence is too low)
        is_approved = confidence_score >= self.confidence_threshold
        decision_action = "EXECUTE" if is_approved else "SKIP"

        # 3. Formulate the textual reasoning
        explanation = self.explainer.generate_explanation(
            symbol=symbol,
            timeframe=timeframe,
            selected_strategy=best_strategy,
            market_regime=current_regime,
            confidence_score=confidence_score,
            confidence_threshold=self.confidence_threshold,
            risk_level=self.risk_level,
            leaderboard=leaderboard
        )

        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 4. Construct the decision payload
        decision_record = {
            "timestamp": timestamp_str,
            "symbol": symbol,
            "timeframe": timeframe,
            "market_regime": current_regime,
            "selected_strategy": best_strategy,
            "confidence_score": confidence_score,
            "decision_action": decision_action,
            "risk_level": self.risk_level,
            "explanation": explanation,
            "parameters": str(best_params)
        }

        # Save to memory and trigger logging
        self.decisions_history.append(decision_record)
        self._log_decision_to_csv(decision_record)

        return decision_record

    def _log_decision_to_csv(self, record: Dict[str, Any]):
        """
        Appends individual AI decisions directly to a CSV file.
        """
        file_exists = os.path.exists(self.log_filepath)
        fieldnames = [
            "timestamp", "symbol", "timeframe", "market_regime", 
            "selected_strategy", "confidence_score", "decision_action", 
            "risk_level", "explanation", "parameters"
        ]

        with open(self.log_filepath, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(record)
