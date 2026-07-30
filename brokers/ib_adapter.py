# brokers/ib_adapter.py
"""
Quantoryx — Interactive Brokers (TWS / Gateway) Broker Adapter.

Adapts IBKR native EClient/EWrapper socket workflows into the async BaseBroker contract [1].
Manages socket message loop threads and synchronizes callback events using asyncio Futures [1, 2].
"""

import os
import sys
import asyncio
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

# Ensure project root is in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from brokers.base import BaseBroker, BrokerAccountInfo, BrokerPosition, BrokerOrderResult
from utils.logging_config import get_logger

logger = get_logger("brokers.ib")

# Defensive import to handle environments missing official ibapi library [4]
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
except ImportError:
    # Build fallback stubs to prevent compilation failure on headless platforms [4]
    class EWrapper: pass
    class EClient:
        def __init__(self, wrapper): pass
    Contract = None
    Order = None
    logger.warning("ibapi library is missing. Install it to activate the Interactive Brokers adapter.")


class IBClient(EWrapper, EClient):
    """
    Subclass of IB's socket client and callback wrapper.
    Intercepts socket events and resolves corresponding async Futures.
    """

    def __init__(self, adapter: "IBAdapter"):
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        self.adapter = adapter

    # =====================================================================
    # ACCOUNT SUMMARY CALLBACKS
    # =====================================================================
    def accountSummary(self, reqId: int, account: str, tag: str, value: str, currency: str):
        """Processes account updates pushed from TWS/Gateway."""
        self.adapter.handle_account_update(tag, value, currency)

    def accountSummaryEnd(self, reqId: int):
        """Triggered when account summary stream is fully cached."""
        self.adapter.resolve_future("account_info")

    # =====================================================================
    # POSITION CALBACKS
    # =====================================================================
    def position(self, account: str, contract, position: float, avgCost: float):
        """Processes active floating positions pushed from TWS/Gateway."""
        self.adapter.handle_position_update(contract, position, avgCost)

    def positionEnd(self):
        """Triggered when active positions are fully cached."""
        self.adapter.resolve_future("positions")

    # =====================================================================
    # ORDER STATUS CALLBACKS
    # =====================================================================
    def orderStatus(self, orderId: int, status: str, filled: float, remaining: float,
                    avgFillPrice: float, permId: int, parentId: int, lastFillPrice: float,
                    clientId: int, whyHeld: str, mktCapPrice: float):
        """Processes live order status state variations."""
        self.adapter.handle_order_status(orderId, status, filled, avgFillPrice)

    # =====================================================================
    # SYSTEM ERROR CALLBACKS
    # =====================================================================
    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str = ""):
        """Handles connection drops or order reject events from the server."""
        logger.error("IB Terminal Error Code: %s | Description: %s", errorCode, errorString)
        # Verify if errorCode represents a connection drop
        if errorCode in [1100, 1101, 1102]:
            self.adapter.is_connected = False
        # Handle order rejection error bounds
        elif reqId > 0:
            self.adapter.reject_order_future(reqId, errorString)


class IBAdapter(BaseBroker):
    """
    Interactive Brokers Adapter.
    Interacts with Trader Workstation (TWS) or IB Gateway running locally [4].
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the IBKR adapter.
        
        Expected Config Parameters:
            - host: str (TWS/Gateway local IP, defaults to '127.0.0.1')
            - port: int (Socket port; standard paper port is 7497, live is 7496)
            - client_id: int (Unique socket identifier, e.g. 1)
            - account_id: str (IB Account ID starting with 'U' or 'DU')
        """
        super().__init__(broker_name="Interactive Brokers", config=config)
        self.host = str(config.get("host", "127.0.0.1"))
        self.port = int(config.get("port", 7497))
        self.client_id = int(config.get("client_id", 1))
        self.account_id = str(config.get("account_id", ""))

        # State and Synchronization structures [2]
        self.client: Optional[IBClient] = None
        self.thread: Optional[threading.Thread] = None
        self.futures: Dict[str, asyncio.Future] = {}
        self.next_order_id = 1000
        
        # Intermediate accumulation buffers
        self.account_cache: Dict[str, Any] = {}
        self.positions_cache: List[BrokerPosition] = []
        self.active_order_futures: Dict[int, asyncio.Future] = {}

    async def authenticate(self) -> bool:
        """Confirms that the host and gateway parameters are present."""
        return Contract is not None and len(self.account_id) > 0

    async def connect(self) -> bool:
        """Connects to the socket interface and launches the client message loop thread [2]."""
        if Contract is None:
            logger.error("Connection aborted: ibapi library is unavailable in this environment [4].")
            return False

        if not await self.authenticate():
            logger.error("Connection aborted: Account ID is missing inside the configuration.")
            return False

        try:
            self.client = IBClient(self)
            self.client.connect(self.host, self.port, self.client_id)
            
            # Start background message reader thread to pump event sockets [2]
            self.thread = threading.Thread(target=self.client.run, daemon=True)
            self.thread.start()

            # Wait slightly to ensure socket handshake stabilizes
            await asyncio.sleep(1.0)
            self.is_connected = self.client.isConnected()

            if self.is_connected:
                logger.info("Interactive Brokers session successfully initialized on port %s for Account %s.", self.port, self.account_id)
                return True
            return False

        except Exception as e:
            logger.error("Failed to connect to IB Gateway: %s", str(e))
            return False

    async def disconnect(self) -> bool:
        """Closes the socket and waits for the message loop thread to terminate [2]."""
        self.is_connected = False
        if self.client:
            self.client.disconnect()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        logger.info("Interactive Brokers session cleanly terminated.")
        return True

    async def check_connection(self) -> bool:
        """Checks socket connection health."""
        if not self.is_connected or self.client is None or not self.client.isConnected():
            return await self.connect()
        return True

    async def get_account_info(self) -> BrokerAccountInfo:
        """Requests and processes account metrics from the local socket."""
        if not self.is_connected or self.client is None:
            raise ConnectionError("IB Gateway is not connected.")

        # Create sync future [2]
        loop = asyncio.get_running_loop()
        self.futures["account_info"] = loop.create_future()
        self.account_cache = {}

        # Request summary (Group: 'All', Tags: Balance, Equity, Margin)
        self.client.reqAccountSummary(9001, "All", "NetLiquidation,TotalCashValue,InitMarginReq,MaintMarginReq")

        try:
            # Wait for EWrapper's accountSummaryEnd callback to resolve the future
            await asyncio.wait_for(self.futures["account_info"], timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Account summary request timed out. Returning cached values.")
        finally:
            self.client.cancelAccountSummary(9001)

        balance = float(self.account_cache.get("TotalCashValue", 0.0))
        equity = float(self.account_cache.get("NetLiquidation", balance))
        margin_used = float(self.account_cache.get("InitMarginReq", 0.0))
        margin_free = max(0.0, equity - margin_used)
        margin_level = (equity / margin_used * 100.0) if margin_used > 0 else float("inf")

        return BrokerAccountInfo(
            account_id=self.account_id,
            balance=balance,
            equity=equity,
            margin_used=margin_used,
            margin_free=margin_free,
            leverage=2.0,  # standard IB Reg-T default leverage multiplier
            currency="USD",
            margin_level_pct=margin_level
        )

    async def get_positions(self) -> List[BrokerPosition]:
        """Requests active positions."""
        if not self.is_connected or self.client is None:
            raise ConnectionError("IB Gateway is not connected.")

        loop = asyncio.get_running_loop()
        self.futures["positions"] = loop.create_future()
        self.positions_cache = []

        self.client.reqPositions()

        try:
            await asyncio.wait_for(self.futures["positions"], timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Positions query timed out.")
        finally:
            self.client.cancelPositions()

        return self.positions_cache

    async def get_symbols(self) -> List[str]:
        """Helper to return a hardcoded list of major forex instruments verified by IBKR."""
        return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURGBP"]

    async def execute_order(self, order_request: Dict[str, Any]) -> BrokerOrderResult:
        """Dispatches an order via EClient.placeOrder and waits for execution status callbacks."""
        if not self.is_connected or self.client is None or Contract is None:
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message="IB Gateway is not connected."
            )

        symbol = order_request.get("symbol", "")
        direction = order_request.get("direction", "BUY").upper()
        volume = float(order_request.get("volume", 0.0))
        order_type_str = order_request.get("order_type", "MARKET").upper()

        # 1. Compile IB Contract
        contract = Contract()
        contract.symbol = symbol[:3]      # e.g., "EUR"
        contract.currency = symbol[3:6]   # e.g., "USD"
        contract.secType = "CASH"
        contract.exchange = "IDEALPRO"

        # 2. Compile IB Order
        order = Order()
        order.action = "BUY" if direction == "BUY" else "SELL"
        order.orderType = order_type_str
        order.totalQuantity = volume
        order.transmit = True

        if order_type_str in ["LIMIT", "STOP"]:
            order.lmtPrice = float(order_request["price"])

        # Create sync future for this orderId
        loop = asyncio.get_running_loop()
        self.next_order_id += 1
        order_id = self.next_order_id
        
        order_future = loop.create_future()
        self.active_order_futures[order_id] = order_future

        # 3. Submit
        self.client.placeOrder(order_id, contract, order)

        try:
            # Wait for orderStatus or error callback to resolve
            result_row = await asyncio.wait_for(order_future, timeout=10.0)
            return result_row
        except asyncio.TimeoutError:
            return BrokerOrderResult(
                order_id=str(order_id),
                success=False,
                status="PENDING",
                error_message="Timeout reached waiting for order fill confirmation from IB Gateway."
            )
        finally:
            self.active_order_futures.pop(order_id, None)

    # =====================================================================
    # INNER CALLBACK STATE SYNCHRONIZATION HELPERS
    # =====================================================================

    def handle_account_update(self, tag: str, value: str, currency: str):
        """Callback caching tags from the account stream."""
        self.account_cache[tag] = value

    def handle_position_update(self, contract, position: float, avgCost: float):
        """Callback mapping open positions."""
        symbol = f"{contract.symbol}{contract.currency}"
        direction = "BUY" if position > 0 else "SELL"
        
        self.positions_cache.append(BrokerPosition(
            position_id=f"ib-pos-{symbol}",
            symbol=symbol,
            direction=direction,
            volume=abs(float(position)),
            entry_price=float(avgCost),
            current_price=float(avgCost)  # standard callback doesn't include current tick
        ))

    def handle_order_status(self, order_id: int, status_str: str, filled: float, avg_price: float):
        """Callback resolving pending order futures on state changes."""
        future = self.active_order_futures.get(order_id)
        if future and not future.done():
            status_upper = status_str.upper()
            if status_upper == "FILLED":
                res = BrokerOrderResult(
                    order_id=str(order_id),
                    success=True,
                    status="FILLED",
                    filled_price=float(avg_price),
                    filled_volume=float(filled)
                )
                future.set_result(res)
            elif status_upper in ["REJECTED", "CANCELLED", "INACTIVE"]:
                res = BrokerOrderResult(
                    order_id=str(order_id),
                    success=False,
                    status=status_upper,
                    error_message=f"Order status updated to: {status_upper}"
                )
                future.set_result(res)

    def reject_order_future(self, order_id: int, error_string: str):
        """Callback resolving pending order futures on explicit reject errors."""
        future = self.active_order_futures.get(order_id)
        if future and not future.done():
            res = BrokerOrderResult(
                order_id=str(order_id),
                success=False,
                status="REJECTED",
                error_message=error_string
            )
            future.set_result(res)

    def resolve_future(self, key: str):
        """Resolves generic synchronous futures cleanly."""
        future = self.futures.get(key)
        if future and not future.done():
            future.set_result(True)
