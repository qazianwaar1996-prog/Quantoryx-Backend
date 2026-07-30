# portfolio/order_manager.py
"""
Quantoryx — Pending Order and OCO Manager.

Tracks pending orders, coordinates OCO (One-Cancels-the-Other) groups,
applies duplicate order checks, and tracks expiries defensively [5].
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.logging_config import get_logger

logger = get_logger("portfolio.orders")


@dataclass
class PendingOrder:
    """Standardized representation of a pending Limit or Stop order."""
    order_id: str
    symbol: str
    direction: str       # BUY or SELL
    order_type: str      # LIMIT or STOP
    volume: float        # Quantity
    price: float         # Target trigger price
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    expiry_time: Optional[datetime] = None
    oco_group_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class OrderManager:
    """
    Manages pending order lifecycles and duplicate trade prevention [5].
    """

    def __init__(self):
        # Map order_id (str) -> PendingOrder object
        self.pending_orders: Dict[str, PendingOrder] = {}
        
        # Map oco_group_id (str) -> list of order_ids (str)
        self.oco_groups: Dict[str, List[str]] = {}

    def add_pending_order(self, order: PendingOrder):
        """Registers a new pending order into the tracking memory [5]."""
        self.pending_orders[order.order_id] = order
        
        # Track OCO mappings if assigned
        if order.oco_group_id:
            group_id = order.oco_group_id
            if group_id not in self.oco_groups:
                self.oco_groups[group_id] = []
            if order.order_id not in self.oco_groups[group_id]:
                self.oco_groups[group_id].append(order.order_id)
                
        logger.debug("Pending order %s registered successfully.", order.order_id)

    def remove_pending_order(self, order_id: str):
        """Removes a pending order from memory following fills or cancellations [5]."""
        order = self.pending_orders.pop(order_id, None)
        if order and order.oco_group_id:
            group_id = order.oco_group_id
            if group_id in self.oco_groups:
                if order_id in self.oco_groups[group_id]:
                    self.oco_groups[group_id].remove(order_id)
                if not self.oco_groups[group_id]:
                    del self.oco_groups[group_id]
                    
        logger.debug("Pending order %s cleared from memory.", order_id)

    # =====================================================================
    # ONE-CANCELS-THE-OTHER (OCO) COORDINATION
    # =====================================================================

    def register_oco_pair(self, order_id_a: str, order_id_b: str, group_id: str):
        """
        Groups two existing pending orders into an OCO relation [5].
        """
        for oid in [order_id_a, order_id_b]:
            if oid in self.pending_orders:
                self.pending_orders[oid].oco_group_id = group_id
                
        self.oco_groups[group_id] = [order_id_a, order_id_b]
        logger.info("OCO relation established under group %s for orders: %s and %s", group_id, order_id_a, order_id_b)

    def handle_order_fill(self, filled_order_id: str) -> List[str]:
        """
        Called when a pending order is filled.
        Returns a list of other order IDs within its OCO group that must now be cancelled [5].
        """
        order = self.pending_orders.get(filled_order_id)
        if not order or not order.oco_group_id:
            self.remove_pending_order(filled_order_id)
            return []

        group_id = order.oco_group_id
        sibling_ids = self.oco_groups.get(group_id, [])
        
        # Identify sister orders that are still pending and need to be cancelled
        orders_to_cancel = [oid for oid in sibling_ids if oid != filled_order_id and oid in self.pending_orders]

        # Purge the entire OCO group from memory
        for oid in sibling_ids:
            self.pending_orders.pop(oid, None)
        self.oco_groups.pop(group_id, None)

        if orders_to_cancel:
            logger.info("OCO Trigger: Order %s filled. Cancelling remaining sibling orders: %s", filled_order_id, orders_to_cancel)
            
        return orders_to_cancel

    # =====================================================================
    # EXPIRY AND DUPLICATE TRADE PROTECTION
    # =====================================================================

    def check_expiries(self, current_time: datetime) -> List[str]:
        """
        Audits pending orders and returns a list of order IDs that have expired [5].
        """
        expired_ids = []
        for oid, order in self.pending_orders.items():
            if order.expiry_time and current_time >= order.expiry_time:
                expired_ids.append(oid)

        for oid in expired_ids:
            self.remove_pending_order(oid)
            logger.info("Pending order %s reached expiry time and was purged.", oid)

        return expired_ids

    def is_duplicate_order(
        self,
        symbol: str,
        direction: str,
        target_price: float,
        price_tolerance_pct: float = 0.05
    ) -> bool:
        """
        Performs a defensive check to block duplicate pending orders [5].
        Returns True if an order already exists for the same asset, direction,
        and within the specified price proximity threshold.
        """
        symbol_upper = symbol.upper()
        direction_upper = direction.upper()

        for order in self.pending_orders.values():
            if order.symbol == symbol_upper and order.direction == direction_upper:
                # Calculate relative proximity distance
                price_distance = abs(order.price - target_price)
                max_allowed_distance = order.price * (price_tolerance_pct / 100.0)
                
                if price_distance <= max_allowed_distance:
                    logger.warning(
                        "Duplicate Protection: Blocked duplicate %s order for %s at price %s. Proximity limit: %s",
                        direction_upper, symbol_upper, target_price, price_tolerance_pct
                    )
                    return True
                    
        return False
