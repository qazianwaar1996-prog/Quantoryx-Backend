# portfolio/position_manager.py
"""
Quantoryx — Position and Portfolio Exposure Manager.

Tracks and aggregates live open positions, floating P/L, commissions, swaps,
margin requirements, and net exposure levels across active broker sessions [4].
"""

import os
import sys
from typing import Dict, List, Optional

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from brokers.base import BrokerAccountInfo, BrokerPosition
from utils.logging_config import get_logger

logger = get_logger("portfolio.positions")


class PositionManager:
    """
    Real-Time open position and exposure monitor.
    Aggregates risk and financial metrics for multiple active open trades [4].
    """

    def __init__(self):
        self.positions: Dict[str, BrokerPosition] = {}
        self.account_id: str = ""
        self.balance: float = 0.0
        self.equity: float = 0.0
        self.margin_used: float = 0.0
        self.margin_free: float = 0.0
        self.leverage: float = 1.0
        self.margin_level_pct: float = float("inf")

    def update_states(self, broker_positions: List[BrokerPosition], account_info: BrokerAccountInfo):
        """
        Updates internal cache memory using active metrics queried from the broker [4].
        """
        self.account_id = account_info.account_id
        self.balance = account_info.balance
        self.equity = account_info.equity
        self.margin_used = account_info.margin_used
        self.margin_free = account_info.margin_free
        self.leverage = account_info.leverage
        self.margin_level_pct = account_info.margin_level_pct

        # Sync active positions dictionary
        current_ids = set()
        for pos in broker_positions:
            self.positions[pos.position_id] = pos
            current_ids.add(pos.position_id)

        # Remove closed/purged positions from cache memory
        purged_ids = [pid for pid in self.positions if pid not in current_ids]
        for pid in purged_ids:
            self.positions.pop(pid, None)

        logger.debug("PositionManager synced. Active Positions: %s | Account Equity: %s", len(self.positions), self.equity)

    # =====================================================================
    # FINANCIAL METRICS AGGREGATIONS
    # =====================================================================

    def get_floating_pnl(self) -> float:
        """Returns cumulative unrealized profit/loss across all open positions."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    def get_total_swap(self) -> float:
        """Returns cumulative accrued swaps (financing fees) across open positions."""
        return sum(pos.swap for pos in self.positions.values())

    def get_total_commission(self) -> float:
        """Returns cumulative commissions paid for initiating open positions."""
        return sum(pos.commission for pos in self.positions.values())

    def get_margin_utilization(self) -> float:
        """Returns the ratio percentage of used margin to total account equity."""
        if self.equity <= 0:
            return 100.0
        return (self.margin_used / self.equity) * 100.0

    # =====================================================================
    # EXPOSURE AND CONCENTRATION RISK METRICS
    # =====================================================================

    def get_exposure_by_symbol(self) -> Dict[str, float]:
        """
        Calculates net exposure per currency pair in base volume units.
        Buying adds positive exposure; selling adds negative exposure.
        """
        exposure_map: Dict[str, float] = {}
        for pos in self.positions.values():
            multiplier = 1.0 if pos.direction == "BUY" else -1.0
            exposure_map[pos.symbol] = exposure_map.get(pos.symbol, 0.0) + (pos.volume * multiplier)
        return exposure_map

    def get_portfolio_exposure_pct(self) -> float:
        """
        Calculates the total absolute exposure (notional value of all trades)
        as a percentage ratio of overall account equity.
        Formula: Total Notional / Equity * 100.0
        """
        if self.equity <= 0:
            return 0.0

        total_notional_usd = 0.0
        for pos in self.positions.values():
            # Estimate notional value in USD.
            # Volume (units) * current_price gives the asset value.
            # For forex pairs, this is in base currency, which provides a reliable risk estimate.
            total_notional_usd += pos.volume * pos.current_price

        return (total_notional_usd / self.equity) * 100.0

    def get_concentration_risk(self) -> Dict[str, float]:
        """
        Measures single-asset concentration ratio percentages relative to overall exposure.
        Identifies if any single pair comprises too much of the risk allocation.
        """
        symbol_notional: Dict[str, float] = {}
        total_notional = 0.0

        for pos in self.positions.values():
            notional = pos.volume * pos.current_price
            symbol_notional[pos.symbol] = symbol_notional.get(pos.symbol, 0.0) + notional
            total_notional += notional

        if total_notional <= 0:
            return {}

        return {symbol: (notional / total_notional * 100.0) for symbol, notional in symbol_notional.items()}
