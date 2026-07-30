# brokers/base.py
"""
Quantoryx — Abstract Broker Adapter Base Interface.

Defines the core contract, transactional methods, and structural models 
required to support uniform multi-broker executions across trading desks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class BrokerAccountInfo:
    """Standardized representation of account balance, margin, and leverage parameters."""
    account_id: str
    balance: float
    equity: float
    margin_used: float
    margin_free: float
    leverage: float
    currency: str = "USD"
    margin_level_pct: float = float("inf")
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BrokerPosition:
    """Standardized representation of an active open trade position in the broker."""
    position_id: str
    symbol: str
    direction: str  # BUY or SELL
    volume: float   # Units/Lots
    entry_price: float
    current_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    swap: float = 0.0
    commission: float = 0.0
    unrealized_pnl: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BrokerOrderResult:
    """Standardized confirmation payload returned upon trade execution attempts."""
    order_id: str
    success: bool
    status: str  # FILLED, REJECTED, PENDING, CANCELLED
    filled_price: Optional[float] = None
    filled_volume: float = 0.0
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BaseBroker(ABC):
    """
    Abstract Base Class establishing the standard interface for external broker APIs.
    All broker-specific adapters must subclass and implement these async handlers.
    """

    def __init__(self, broker_name: str, config: Dict[str, Any]):
        self.broker_name = broker_name
        self.config = config
        self.is_connected = False

    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Validates authentication parameters against the broker gateway.
        Returns True if credentials are verified, False otherwise.
        """
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establishes an active connection session (REST/WebSockets/TCP) with the broker.
        Handles initial authentication and channel subscription steps.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Closes connection channels, releases socket bindings, and cleanly terminates the session.
        """
        pass

    @abstractmethod
    async def check_connection(self) -> bool:
        """
        Actively pings or audits connection state integrity.
        Performs automated reconnection logic if disconnects are detected.
        """
        pass

    @abstractmethod
    async def get_account_info(self) -> BrokerAccountInfo:
        """
        Queries and returns the current authenticated account balance, equity, and margin levels.
        """
        pass

    @abstractmethod
    async def get_positions(self) -> List[BrokerPosition]:
        """
        Queries and returns all currently open, active trade positions.
        """
        pass

    @abstractmethod
    async def get_symbols(self) -> List[str]:
        """
        Queries and returns the list of tradable symbols/instruments supported by this broker.
        """
        pass

    @abstractmethod
    async def execute_order(self, order_request: Dict[str, Any]) -> BrokerOrderResult:
        """
        Submits an order execution request (market, limit, stop) to the broker gateway.
        
        Parameters:
            order_request: Dict containing:
                - symbol: str (e.g., "EURUSD")
                - direction: str ("BUY" or "SELL")
                - volume: float (size)
                - order_type: str ("MARKET", "LIMIT", "STOP")
                - price: Optional[float] (for limit/stop orders)
                - stop_loss: Optional[float]
                - take_profit: Optional[float]
                - slippage: Optional[float] (slippage tolerance)
        """
        pass
