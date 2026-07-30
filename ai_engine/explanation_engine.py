# ai_engine/explanation_engine.py

from typing import Dict, Any


class ExplanationEngine:
    """
    Formulates structured, quantitative, and narrative justifications 
    behind the AI Decision Engine's selections and trade skips.
    """
    def __init__(self):
        pass

    def generate_explanation(
        self,
        symbol: str,
        timeframe: str,
        selected_strategy: str,
        market_regime: str,
        confidence_score: float,
        confidence_threshold: float,
        risk_level: str,
        leaderboard: Dict[str, float],
        reason_code: str = "COMPATIBILITY_OPTIMUM"
    ) -> str:
        """
        Builds a comprehensive, readable string detailing the mathematical 
        and structural logic behind the model selection decision.
        """
        # Determine the status of the decision
        is_skipped = confidence_score < confidence_threshold
        decision_status = "TRADE_SKIPPED" if is_skipped else "STRATEGY_EXECUTED"

        # Map reason codes to clear templates
        if is_skipped:
            core_reason = (
                f"The highest scoring strategy, {selected_strategy}, achieved a confidence score of "
                f"{confidence_score}, which is below the required execution threshold of {confidence_threshold}."
            )
        else:
            core_reason = (
                f"Nominated {selected_strategy} as the primary trading model because its confidence score of "
                f"{confidence_score} successfully exceeded the filter threshold of {confidence_threshold}."
            )

        # Build leader string
        leader_runs = [f"{strat}: {score:.1f}" for strat, score in sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)]
        leaderboard_str = ", ".join(leader_runs)

        # Generate descriptive paragraph
        explanation = (
            f"[{decision_status}] Asset Context: {symbol} ({timeframe}). "
            f"Classified Market Regime: '{market_regime}'. Risk Level Assigned: '{risk_level}'. "
            f"{core_reason} "
            f"Reasoning Matrix: Under '{market_regime}' conditions, the selection score represents a blend "
            f"of historical Walk-Forward performance and structural regime compatibility coefficients. "
            f"Leaderboard runs evaluated: [{leaderboard_str}]."
        )

        return explanation
