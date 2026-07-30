# execution/executor.py
"""
Quantoryx — Trade Execution Engine Controller.

Sits directly on top of BaseBroker adapters to coordinate and secure order execution.
Features retry handlers, slippage validation, and partial closing state management [3].
"""

import os
import sys
import asyncio
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

# Ensure project root is in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from brokers.base import BaseBroker, BrokerOrderResult, BrokerPosition
from utils.logging_config import get_logger

logger = get_logger("execution.engine")


class ExecutionEngine:
    """
    Unified Execution Engine Controller.
    Manages order lifecycles and handles order modifications defensively [3].
    """

    def __init__(
        self,
        broker: BaseBroker,
        max_retries: int = 3,
        retry_delay_seconds: float = 0.5,
        default_slippage_pips: int = 10
    ):
        """
        Initializes the execution engine.
        
        Parameters:
            broker: An active, authenticated instance subclassing BaseBroker.
            max_retries: Number of attempts to submit an order before declaring failure [3].
            retry_delay_seconds: Sleep delay interval between retry attempts [3].
            default_slippage_pips: Standard slippage deviation limits for market fills.
        """
        self.broker = broker
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.default_slippage_pips = default_slippage_pips

    # =====================================================================
    # CORE ORDER SUBMISSION PIPELINES (With Retries)
    # =====================================================================

    async def submit_market_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        slippage_pips: Optional[int] = None
    ) -> BrokerOrderResult:
        """Submits a standardized Market Order with built-in retry and slippage guardrails [3]."""
        self._validate_trade_bounds(direction, stop_loss, take_profit)

        order_request = {
            "symbol": symbol.upper(),
            "direction": direction.upper(),
            "volume": float(volume),
            "order_type": "MARKET",
            "slippage": slippage_pips if slippage_pips is not None else self.default_slippage_pips
        }

        if stop_loss is not None:
            order_request["stop_loss"] = float(stop_loss)
        if take_profit is not None:
            order_request["take_profit"] = float(take_profit)

        return await self._execute_with_retries(order_request)

    async def submit_limit_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        limit_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> BrokerOrderResult:
        """Submits a pending Limit Order with built-in retry checks [3]."""
        self._validate_trade_bounds(direction, stop_loss, take_profit)

        order_request = {
            "symbol": symbol.upper(),
            "direction": direction.upper(),
            "volume": float(volume),
            "order_type": "LIMIT",
            "price": float(limit_price)
        }

        if stop_loss is not None:
            order_request["stop_loss"] = float(stop_loss)
        if take_profit is not None:
            order_request["take_profit"] = float(take_profit)

        return await self._execute_with_retries(order_request)

    async def submit_stop_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        stop_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> BrokerOrderResult:
        """Submits a pending Stop Order with built-in retry checks [3]."""
        self._validate_trade_bounds(direction, stop_loss, take_profit)

        order_request = {
            "symbol": symbol.upper(),
            "direction": direction.upper(),
            "volume": float(volume),
            "order_type": "STOP",
            "price": float(stop_price)
        }

        if stop_loss is not None:
            order_request["stop_loss"] = float(stop_loss)
        if take_profit is not None:
            order_request["take_profit"] = float(take_profit)

        return await self._execute_with_retries(order_request)

    # =====================================================================
    # POSITION AND LIMIT MODIFICATION ACTIONS
    # =====================================================================

    async def modify_position_sl_tp(
        self,
        position_id: str,
        symbol: str,
        stop_loss: Optional[float],
        take_profit: Optional[float]
    ) -> BrokerOrderResult:
        """
        Modifies the Stop Loss and Take Profit thresholds of an active open position [3].
        """
        order_request = {
            "action": "MODIFY_POSITION",
            "position_id": position_id,
            "symbol": symbol.upper(),
            "stop_loss": stop_loss,
            "take_profit": take_profit
        }
        
        logger.info("Modifying position %s SL/TP levels to SL: %s | TP: %s", position_id, stop_loss, take_profit)
        return await self._execute_with_retries(order_request)

    async def close_position_fully(self, position: BrokerPosition) -> BrokerOrderResult:
        """
        Fully closes an active open position by submitting an opposite transaction [3].
        """
        logger.info("Executing full closure request for position %s (Vol: %s)", position.position_id, position.volume)
        
        # Determine the opposite closure action required
        opposite_direction = "SELL" if position.direction == "BUY" else "BUY"

        order_request = {
            "symbol": position.symbol,
            "direction": opposite_direction,
            "volume": position.volume,
            "order_type": "MARKET",
            "comment": f"Close position {position.position_id}"
        }

        return await self._execute_with_retries(order_request)

    async def close_position_partially(self, position: BrokerPosition, close_volume: float) -> BrokerOrderResult:
        """
        Partially closes an active open position by submitting an opposite transaction [3].
        
        Parameters:
            position: The target BrokerPosition structure being modified.
            close_volume: The fraction of volume to close (e.g. if position has 1.0 lot and we close 0.3 lot).
        """
        if close_volume >= position.volume:
            logger.warning("Partial close volume %s exceeds position volume %s. Running full close instead.", close_volume, position.volume)
            return await self.close_position_fully(position)

        logger.info("Executing partial closure request for position %s (Close Vol: %s / Total Vol: %s)", position.position_id, close_volume, position.volume)
        
        opposite_direction = "SELL" if position.direction == "BUY" else "BUY"

        order_request = {
            "symbol": position.symbol,
            "direction": opposite_direction,
            "volume": float(close_volume),
            "order_type": "MARKET",
            "comment": f"Partial close position {position.position_id}"
        }

        return await self._execute_with_retries(order_request)

    # =====================================================================
    # INNER RETRY & TRANSACTION AUDITING ENGINE (Execution Logging)
    # =====================================================================

    async def _execute_with_retries(self, order_request: Dict[str, Any]) -> BrokerOrderResult:
        """
        Asynchronously submits an order request to the broker gateway.
        Retries up to max_retries on transient socket/gateway drops [2, 3].
        """
        start_time = time.perf_counter()
        attempt_result = None

        for attempt in range(1, self.max_retries + 1):
            try:
                # Active connection health check before submission
                await self.broker.check_connection()

                # Dispatch order send to the adapter
                attempt_result = await self.broker.execute_order(order_request)
                
                # Check outcome success status
                if attempt_result.success:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    logger.info(
                        "Execution Success: %s %s %s filled at price %s in %s ms (Attempt %s).",
                        order_request.get("direction", "ORDER"),
                        order_request.get("volume", ""),
                        order_request.get("symbol", ""),
                        attempt_result.filled_price,
                        round(duration_ms, 2),
                        attempt
                    )
                    return attempt_result
                else:
                    logger.warning(
                        "Execution Attempt %s Rejected: %s. retrying...",
                        attempt,
                        attempt_result.error_message
                    )

            except Exception as e:
                logger.error("Exception caught on execution attempt %s: %s", attempt, str(e), exc_info=True)
                attempt_result = BrokerOrderResult(
                    order_id="",
                    success=False,
                    status="REJECTED",
                    error_message=f"Exception triggered: {str(e)}"
                )

            # Wait before attempting a reconnect/retry sequence
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay_seconds * attempt)  # linear backoff delay increase

        # If we loop out, return the final rejection result
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error(
            "Execution Failure: Order aborted after %s failed retry attempts. Total latency: %s ms. Final Error: %s",
            self.max_retries,
            round(duration_ms, 2),
            attempt_result.error_message if attempt_result else "No connection"
        )
        return attempt_result

    def _validate_trade_bounds(self, direction: str, sl: Optional[float], tp: Optional[float]):
        """
        Defensive safety verification checking logical SL/TP placements before execution [3].
        """
        if direction.upper() == "BUY":
            if sl is not None and sl >= tp if tp is not None else False:
                raise ValueError("Logical Error: Long order stop-loss cannot exceed take-profit.")
        elif direction.upper() == "SELL":
            if sl is not None and sl <= tp if tp is not None else False:
                raise ValueError("Logical Error: Short order stop-loss cannot fall below take-profit.")
