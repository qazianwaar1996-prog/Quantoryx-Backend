# brokers/mt5_adapter.py
"""
Quantoryx — MetaTrader 5 Broker Adapter.

Adapts local MetaTrader 5 terminal operations into the BaseBroker interface contract.
Uses asynchronous execution wrappers over synchronous terminal calls to prevent thread blocking [1].
"""

import os
import sys
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

# Ensure project root is in search path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from brokers.base import BaseBroker, BrokerAccountInfo, BrokerPosition, BrokerOrderResult
from utils.logging_config import get_logger

logger = get_logger("brokers.mt5")

# Defensive import to handle non-Windows runtime deployment platforms cleanly [4]
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None
    logger.warning("MetaTrader5 library is not installed or unavailable in this environment.")


class MT5Adapter(BaseBroker):
    """
    MT5 broker interface adapter.
    Interacts with the locally running MT5 terminal instance over standard IPC channels [4].
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the MT5 terminal interface.
        
        Expected Config Parameters:
            - login: int (MT5 account login number)
            - password: str (Account trading password)
            - server: str (Broker server domain/IP)
            - path: Optional[str] (Absolute filesystem path to terminal.exe)
        """
        super().__init__(broker_name="MetaTrader 5", config=config)
        self.login = int(config.get("login", 0))
        self.password = str(config.get("password", ""))
        self.server = str(config.get("server", ""))
        self.terminal_path = config.get("path", None)

    async def authenticate(self) -> bool:
        """Confirms database login viability without fully binding connections."""
        if mt5 is None:
            logger.error("Authentication rejected: MetaTrader 5 library is unavailable in this OS context [4].")
            return False
        
        # Test terminal startup properties
        return self.login > 0 and len(self.password) > 0 and len(self.server) > 0

    async def connect(self) -> bool:
        """Spins up the terminal connection thread and performs server authentication."""
        if mt5 is None:
            logger.error("Terminal initialization aborted: MT5 library not found.")
            return False

        try:
            # Wrap blocking initialization into a separate thread pool to preserve ASGI loops [1, 2]
            init_args = {}
            if self.terminal_path:
                init_args["path"] = self.terminal_path
            if self.server:
                init_args["server"] = self.server

            initialized = await asyncio.to_thread(mt5.initialize, **init_args)
            if not initialized:
                err_code, err_desc = mt5.last_error()
                logger.error("MT5 initialization failed. Error Code: %s (%s)", err_code, err_desc)
                return False

            # Authenticate account login parameters
            logged_in = await asyncio.to_thread(
                mt5.login,
                login=self.login,
                password=self.password,
                server=self.server
            )

            if not logged_in:
                err_code, err_desc = mt5.last_error()
                logger.error("MT5 server authentication failed for account %s. Error: %s (%s)", self.login, err_code, err_desc)
                await asyncio.to_thread(mt5.shutdown)
                return False

            self.is_connected = True
            logger.info("MetaTrader 5 terminal connection established for Account %s on Server %s", self.login, self.server)
            return True

        except Exception as e:
            logger.error("An unexpected error occurred during MT5 terminal connection: %s", str(e))
            return False

    async def disconnect(self) -> bool:
        """Shutdown the MT5 API connection."""
        if mt5 is not None and self.is_connected:
            await asyncio.to_thread(mt5.shutdown)
        self.is_connected = False
        logger.info("MetaTrader 5 connection cleanly terminated.")
        return True

    async def check_connection(self) -> bool:
        """Verifies terminal connection health and triggers auto-reconnects if required."""
        if mt5 is None or not self.is_connected:
            return False

        try:
            terminal_info = await asyncio.to_thread(mt5.terminal_info)
            if terminal_info is None or not terminal_info.connected:
                logger.warning("MT5 terminal connection dropped. Triggering automatic reconnection...")
                self.is_connected = False
                return await self.connect()
            return True
        except Exception as e:
            logger.error("Error during MT5 connection audit check: %s", str(e))
            self.is_connected = False
            return False

    async def get_account_info(self) -> BrokerAccountInfo:
        """Retrieves active account details."""
        if mt5 is None or not self.is_connected:
            raise ConnectionError("MetaTrader 5 terminal is not connected.")

        acc_info = await asyncio.to_thread(mt5.account_info)
        if acc_info is None:
            err_code, err_desc = mt5.last_error()
            raise ValueError(f"Failed to retrieve MT5 account info. Error: {err_code} ({err_desc})")

        # Map to unified schema
        margin_level = (acc_info.equity / acc_info.margin * 100.0) if acc_info.margin > 0 else float("inf")

        return BrokerAccountInfo(
            account_id=str(acc_info.login),
            balance=float(acc_info.balance),
            equity=float(acc_info.equity),
            margin_used=float(acc_info.margin),
            margin_free=float(acc_info.margin_free),
            leverage=float(acc_info.leverage),
            currency=acc_info.currency,
            margin_level_pct=margin_level
        )

    async def get_positions(self) -> List[BrokerPosition]:
        """Queries active floating transactions from the terminal."""
        if mt5 is None or not self.is_connected:
            raise ConnectionError("MetaTrader 5 terminal is not connected.")

        raw_positions = await asyncio.to_thread(mt5.positions_get)
        if raw_positions is None:
            err_code, err_desc = mt5.last_error()
            logger.error("Failed to query active positions. Error: %s (%s)", err_code, err_desc)
            return []

        positions_list = []
        for pos in raw_positions:
            direction = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
            
            positions_list.append(BrokerPosition(
                position_id=str(pos.ticket),
                symbol=pos.symbol,
                direction=direction,
                volume=float(pos.volume),
                entry_price=float(pos.price_open),
                current_price=float(pos.price_current),
                stop_loss=float(pos.sl) if pos.sl > 0 else None,
                take_profit=float(pos.tp) if pos.tp > 0 else None,
                swap=float(pos.swap),
                commission=float(pos.commission),
                unrealized_pnl=float(pos.profit)
            ))

        return positions_list

    async def get_symbols(self) -> List[str]:
        """Queries all trade instruments available on the server broker."""
        if mt5 is None or not self.is_connected:
            raise ConnectionError("MetaTrader 5 terminal is not connected.")

        raw_symbols = await asyncio.to_thread(mt5.symbols_get)
        if raw_symbols is None:
            return []
        return [sym.name for sym in raw_symbols]

    async def execute_order(self, order_request: Dict[str, Any]) -> BrokerOrderResult:
        """Dispatches trade execution requests cleanly inside MT5's IPC pipeline."""
        if mt5 is None or not self.is_connected:
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message="MetaTrader 5 terminal is not connected."
            )

        symbol = order_request.get("symbol", "")
        direction = order_request.get("direction", "BUY").upper()
        volume = float(order_request.get("volume", 0.0))
        order_type_str = order_request.get("order_type", "MARKET").upper()
        slippage = int(order_request.get("slippage", 10))

        # 1. Map direction into MT5 order action indices
        action_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

        # 2. Get current price context to supply if using market or limit orders
        tick = await asyncio.to_thread(mt5.symbol_info_tick, symbol)
        if tick is None:
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message=f"Failed to query tick info for symbol: {symbol}"
            )

        price = float(order_request.get("price", tick.ask if direction == "BUY" else tick.bid))

        # 3. Construct the official trade request payload
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": action_type,
            "price": price,
            "deviation": slippage,
            "magic": 1002026,  # Magic Number trace ID
            "comment": "Quantoryx v5.0 Execution",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Setup custom SL/TP boundaries if provided
        if order_request.get("stop_loss") is not None:
            request["sl"] = float(order_request["stop_loss"])
        if order_request.get("take_profit") is not None:
            request["tp"] = float(order_request["take_profit"])

        # 4. Dispatch the deal request to MT5 terminal
        result = await asyncio.to_thread(mt5.order_send, request)

        if result is None:
            err_code, err_desc = mt5.last_error()
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message=f"Order submission returned null. Terminal error: {err_code} ({err_desc})"
            )

        # 5. Parse execution response codes
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return BrokerOrderResult(
                order_id=str(result.order) if result.order > 0 else "",
                success=False,
                status="REJECTED",
                error_message=f"MT5 order rejected. Code: {result.retcode} | Desc: {result.comment}"
            )

        return BrokerOrderResult(
            order_id=str(result.order),
            success=True,
            status="FILLED",
            filled_price=float(result.price),
            filled_volume=float(result.volume)
        )
