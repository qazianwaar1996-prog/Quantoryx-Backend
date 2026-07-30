# portfolio/optimizer.py
"""
Quantoryx — Portfolio Risk and Capital Optimizer.

Provides mathematical frameworks (Kelly, Risk Parity, Volatility Allocation)
and drawdown constraints to calculate risk-adjusted position sizes [6].
"""

import os
import sys
from typing import Dict, List, Optional
import numpy as np

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.logging_config import get_logger

logger = get_logger("portfolio.optimizer")


class PortfolioOptimizer:
    """
    Mathematical capital and risk allocator [6].
    """

    @staticmethod
    def calculate_kelly_size(win_rate: float, win_loss_ratio: float, fraction: float = 0.5) -> float:
        """
        Computes the Kelly Criterion allocation size [6].
        Uses a fractional scaling factor (e.g. half-Kelly) to prevent aggressive drawdowns.
        
        Formula: f* = (p * (b + 1) - 1) / b
        Where:
            p = win_rate (0.0 to 1.0)
            b = win_loss_ratio (Gross Profit / Gross Loss)
            fraction = Kelly fraction to apply (defaults to 0.50 for Half-Kelly)
        """
        if win_rate <= 0 or win_rate >= 1.0 or win_loss_ratio <= 0:
            return 0.0

        # Kelly Formula
        kelly_f = (win_rate * (win_loss_ratio + 1) - 1) / win_loss_ratio
        
        # Apply fractional scaling and cap to guard boundaries (max 25% allocation on any single run)
        scaled_kelly = max(0.0, kelly_f * fraction)
        return min(0.25, scaled_kelly)

    @staticmethod
    def calculate_risk_parity_weights(volatilities: List[float]) -> List[float]:
        """
        Computes portfolio weights where risk is balanced inversely proportional to volatility [6].
        
        Formula: w_i = (1 / vol_i) / Sum(1 / vol_j)
        """
        if not volatilities:
            return []

        # Convert to numpy and guard against zero standard deviation values
        vols = np.array(volatilities, dtype=float)
        vols = np.where(vols <= 0.0, 1e-6, vols)

        # Inverse of volatility
        inv_vols = 1.0 / vols
        sum_inv = np.sum(inv_vols)

        if sum_inv <= 0:
            return [1.0 / len(volatilities)] * len(volatilities)

        weights = inv_vols / sum_inv
        return weights.tolist()

    @staticmethod
    def calculate_volatility_allocation_size(
        balance: float,
        daily_volatility_pct: float,
        target_risk_pct: float = 1.0
    ) -> float:
        """
        Allocates sizing proportional to asset volatility [6].
        Instruments with higher daily volatility get smaller lot sizes.
        
        Formula: Allowed Capital = (Balance * Target Risk) / Daily Volatility
        """
        if daily_volatility_pct <= 0 or balance <= 0:
            return 0.0

        # Convert percentages to decimals
        target_risk = target_risk_pct / 100.0
        volatility = daily_volatility_pct / 100.0

        allowed_capital_usd = (balance * target_risk) / volatility
        return allowed_capital_usd

    @staticmethod
    def apply_drawdown_constraint_scale(current_drawdown_pct: float, max_drawdown_limit: float) -> float:
        """
        Applies a defensive risk constraint scale based on current account drawdown [6].
        As the account's cumulative drawdown approaches its limit, position sizes are
        scaled down linearly to preserve capital.
        
        Formula: Scale = 1.0 - (Current DD / Max DD Limit)
        """
        if max_drawdown_limit <= 0:
            return 1.0

        if current_drawdown_pct >= max_drawdown_limit:
            logger.warning("Drawdown limit breached (%s / %s). Sizing scaled to 0.0.", current_drawdown_pct, max_drawdown_limit)
            return 0.0

        # Linear decay scaling factor
        scale_factor = 1.0 - (current_drawdown_pct / max_drawdown_limit)
        return max(0.0, min(1.0, scale_factor))

    @classmethod
    def optimize_position_size(
        cls,
        balance: float,
        win_rate: float,
        win_loss_ratio: float,
        current_drawdown_pct: float,
        max_drawdown_limit: float,
        asset_volatility_pct: float,
        target_risk_pct: float = 1.0,
        kelly_fraction: float = 0.5
    ) -> float:
        """
        Synthesizes multiple allocation models to return an optimized position size [6].
        Combines Fractional Kelly, Volatility sizing, and Drawdown constraint scales.
        """
        if balance <= 0:
            return 0.0

        # 1. Base Sizing using Volatility Sizing Model
        vol_size_usd = cls.calculate_volatility_allocation_size(
            balance=balance,
            daily_volatility_pct=asset_volatility_pct,
            target_risk_pct=target_risk_pct
        )

        # 2. Adjust using Fractional Kelly multipliers
        kelly_multiplier = cls.calculate_kelly_size(
            win_rate=win_rate,
            win_loss_ratio=win_loss_ratio,
            fraction=kelly_fraction
        )
        
        # If Kelly is 0 (unfavorable win rate/ratio), we fallback to a minimal risk multiplier (e.g. 0.10)
        kelly_factor = kelly_multiplier if kelly_multiplier > 0 else 0.10

        # 3. Apply defensive drawdown constraints scale
        drawdown_scale = cls.apply_drawdown_constraint_scale(
            current_drawdown_pct=current_drawdown_pct,
            max_drawdown_limit=max_drawdown_limit
        )

        # 4. Integrate all models
        optimized_allocation_usd = vol_size_usd * kelly_factor * drawdown_scale

        logger.debug(
            "Sizing Optimized. Base Vol Size: %s | Kelly Mult: %s | DD Scale: %s | Final Size: %s",
            round(vol_size_usd, 2), round(kelly_factor, 3), round(drawdown_scale, 2), round(optimized_allocation_usd, 2)
        )

        # Cap the maximum allocation to 20% of account balance as an absolute safety threshold
        max_cap = balance * 0.20
        return min(max_cap, optimized_allocation_usd)
