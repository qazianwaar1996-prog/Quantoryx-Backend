# risk_rating/strategy_rater.py
"""
Quantoryx Strategy Risk Rating Engine.

Gives every strategy a comprehensive risk profile — like a credit
score but for trading strategies. Traders see this before
subscribing to marketplace strategies or going live.

Dimensions rated (each 0–100, higher = riskier):
  1. Drawdown Risk      — how deep can it go?
  2. Consistency Risk   — how stable is performance?
  3. Regime Risk        — does it fail in certain regimes?
  4. Tail Risk          — probability of catastrophic loss?
  5. Overfitting Risk   — is it curve-fitted to history?
  6. Spread Sensitivity — does it break with wider spreads?
  7. Sample Size Risk   — enough trades to trust the stats?

Composite: weighted average → letter grade A/B/C/D/F
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class RiskDimension:
    name: str
    score: int        # 0–100 (higher = more risky)
    grade: str        # A–F
    detail: str


@dataclass
class StrategyRiskRating:
    strategy_name: str
    overall_score: int      # 0–100 (composite risk)
    overall_grade: str      # A / B / C / D / F
    overall_label: str      # "Low Risk" / "Medium" / "High" / "Very High" / "Extreme"
    dimensions: List[RiskDimension]
    pass_for_live: bool     # our recommendation: ready for live trading?
    warnings: List[str]
    strengths: List[str]
    summary: str


class StrategyRiskRater:
    """
    Produces a full risk rating for any strategy backtest result.

    Usage:
        rater = StrategyRiskRater()
        rating = rater.rate(
            strategy_name="supertrend",
            backtest_results=engine.results,
            equity_curve=[100000, 100850, ...],
            regime_breakdown={"Trending": 0.6, "Ranging": 0.3, "High Volatility": 0.1},
        )
    """

    DIMENSION_WEIGHTS = {
        "drawdown":    0.25,
        "consistency": 0.20,
        "tail":        0.20,
        "regime":      0.15,
        "overfitting": 0.10,
        "spread":      0.05,
        "sample":      0.05,
    }

    def rate(
        self,
        strategy_name: str,
        backtest_results: Dict,
        equity_curve: Optional[List[float]] = None,
        regime_breakdown: Optional[Dict[str, float]] = None,
        spread_sensitivity_results: Optional[Dict[float, float]] = None,  # {spread_mult: sharpe}
    ) -> StrategyRiskRating:

        dims: List[RiskDimension] = []

        # ── 1. Drawdown Risk ──────────────────────────────────────────
        dd = abs(float(backtest_results.get("max_drawdown_pct", 0)))
        dd_score = int(min(100, dd * 4))   # 25% DD = 100 score
        dims.append(RiskDimension(
            name="Drawdown Risk", score=dd_score,
            grade=self._grade(dd_score),
            detail=f"Max drawdown: {dd:.1f}%. {'Acceptable' if dd < 15 else 'High' if dd < 25 else 'Very high'}.",
        ))

        # ── 2. Consistency Risk ───────────────────────────────────────
        if equity_curve and len(equity_curve) > 10:
            ec = pd.Series(equity_curve)
            returns = ec.pct_change().dropna()
            cv = float(returns.std() / abs(returns.mean())) if returns.mean() != 0 else 10
            cons_score = int(min(100, cv * 20))
        else:
            pf = float(backtest_results.get("profit_factor", 1.0))
            cons_score = int(max(0, min(100, (2.0 - pf) * 50)))
        dims.append(RiskDimension(
            name="Consistency Risk", score=cons_score,
            grade=self._grade(cons_score),
            detail=f"Return volatility coefficient: {'Low' if cons_score < 30 else 'Medium' if cons_score < 60 else 'High'}.",
        ))

        # ── 3. Tail Risk ──────────────────────────────────────────────
        if equity_curve and len(equity_curve) > 20:
            ec = pd.Series(equity_curve)
            returns = ec.pct_change().dropna()
            var_5 = float(returns.quantile(0.05))
            cvar_5 = float(returns[returns <= var_5].mean()) if (returns <= var_5).any() else var_5
            tail_score = int(min(100, abs(cvar_5) * 2000))
        else:
            tail_score = int(min(100, dd * 3))
        dims.append(RiskDimension(
            name="Tail Risk", score=tail_score,
            grade=self._grade(tail_score),
            detail=f"Worst-case scenario risk. {'Manageable' if tail_score < 40 else 'Elevated' if tail_score < 70 else 'Severe'}.",
        ))

        # ── 4. Regime Risk ────────────────────────────────────────────
        if regime_breakdown:
            hv_pct = regime_breakdown.get("High Volatility", 0.0)
            regime_score = int(min(100, hv_pct * 200))  # 50% in HV = 100
        else:
            regime_score = 30  # unknown = medium
        dims.append(RiskDimension(
            name="Regime Risk", score=regime_score,
            grade=self._grade(regime_score),
            detail=f"{'Low exposure' if regime_score < 30 else 'Moderate exposure' if regime_score < 60 else 'High exposure'} to adverse market regimes.",
        ))

        # ── 5. Overfitting Risk ───────────────────────────────────────
        n_trades = int(backtest_results.get("total_trades", 0))
        n_params = int(backtest_results.get("param_count", 2))
        if n_trades > 0:
            ratio = n_trades / max(1, n_params)
            of_score = int(max(0, min(100, 100 - ratio * 2)))  # 50 trades/param = 0 risk
        else:
            of_score = 80
        dims.append(RiskDimension(
            name="Overfitting Risk", score=of_score,
            grade=self._grade(of_score),
            detail=f"{n_trades} trades / {n_params} parameters = {'Low' if of_score < 30 else 'Medium' if of_score < 60 else 'High'} overfitting risk.",
        ))

        # ── 6. Spread Sensitivity ─────────────────────────────────────
        if spread_sensitivity_results:
            base = list(spread_sensitivity_results.values())[0]
            worst = min(spread_sensitivity_results.values())
            if base != 0:
                deg = (base - worst) / abs(base)
                sp_score = int(min(100, deg * 100))
            else:
                sp_score = 50
        else:
            sp_score = 25  # unknown = low-medium
        dims.append(RiskDimension(
            name="Spread Sensitivity", score=sp_score,
            grade=self._grade(sp_score),
            detail=f"{'Low' if sp_score < 30 else 'Medium' if sp_score < 60 else 'High'} sensitivity to spread widening.",
        ))

        # ── 7. Sample Size Risk ───────────────────────────────────────
        if n_trades >= 200:    samp_score = 5
        elif n_trades >= 100:  samp_score = 20
        elif n_trades >= 50:   samp_score = 40
        elif n_trades >= 20:   samp_score = 65
        else:                  samp_score = 90
        dims.append(RiskDimension(
            name="Sample Size Risk", score=samp_score,
            grade=self._grade(samp_score),
            detail=f"{n_trades} trades. {'Statistically significant' if n_trades >= 100 else 'More data needed' if n_trades >= 30 else 'Insufficient sample — treat with caution'}.",
        ))

        # ── Composite Score ───────────────────────────────────────────
        dim_map = {
            "drawdown": dims[0], "consistency": dims[1], "tail": dims[2],
            "regime": dims[3], "overfitting": dims[4], "spread": dims[5], "sample": dims[6],
        }
        composite = int(sum(
            dim_map[k].score * w for k, w in self.DIMENSION_WEIGHTS.items()
        ))

        overall_grade = self._grade(composite)
        label_map = {
            "A": "Low Risk", "B": "Moderate Risk", "C": "Elevated Risk",
            "D": "High Risk", "F": "Extreme Risk",
        }
        label = label_map.get(overall_grade, "Unknown")

        # ── Warnings and Strengths ────────────────────────────────────
        warnings = [d.detail for d in dims if d.score >= 60]
        strengths = [d.detail for d in dims if d.score <= 25]
        pass_live = composite < 55 and samp_score < 65

        summary = (
            f"{strategy_name.replace('_',' ').title()} scores {composite}/100 risk ({label}). "
            f"{'Ready for live trading with standard position sizing.' if pass_live else 'Recommend further backtesting or paper trading before going live.'}"
        )

        return StrategyRiskRating(
            strategy_name=strategy_name,
            overall_score=composite,
            overall_grade=overall_grade,
            overall_label=label,
            dimensions=dims,
            pass_for_live=pass_live,
            warnings=warnings[:3],
            strengths=strengths[:3],
            summary=summary,
        )

    def compare(self, ratings: List[StrategyRiskRating]) -> List[Dict]:
        """Return sorted comparison of multiple strategy ratings."""
        return sorted([
            {
                "strategy": r.strategy_name,
                "score": r.overall_score,
                "grade": r.overall_grade,
                "label": r.overall_label,
                "pass_live": r.pass_for_live,
            }
            for r in ratings
        ], key=lambda x: x["score"])

    def _grade(self, score: int) -> str:
        if score <= 20: return "A"
        if score <= 40: return "B"
        if score <= 60: return "C"
        if score <= 80: return "D"
        return "F"
