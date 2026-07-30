# brokers/dxtrade_adapter.py
"""
Quantoryx — DXtrade REST Broker Adapter.

Adapts DXtrade gateway JSON-REST operations into the BaseBroker interface contract.
Uses asynchronous ClientSession handlers to prevent blocking the core ASGI threads [1, 2].
"""

import os
import sys
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

# Ensure project root is in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from brokers.base import BaseBroker, BrokerAccountInfo, BrokerPosition, BrokerOrderResult
from utils.logging_config import get_logger

logger = get_logger("brokers.dxtrade")

# Defensive import to handle environments missing aiohttp cleanly [4]
try:
    import aiohttp
except ImportError:
    aiohttp = None
    logger.warning("aiohttp library is missing. Install it to activate the DXtrade broker adapter.")


class DXtradeAdapter(BaseBroker):
    """
    DXtrade Broker Interface Adapter.
    Communicates via standard JSON-REST API paths using proprietary DXToken session authentication [4].
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the DXtrade adapter.
        
        Expected Config Parameters:
            - server_url: str (Base URL of the broker API, e.g. https://dxtrade.mybroker.com)
            - username: str (Account login handle)
            - password: str (Account password)
            - account_id: str (Target account identifier)
            - domain: Optional[str] (Optional login domain parameter, defaults to "default")
        """
        super().__init__(broker_name="DXtrade", config=config)
        self.server_url = str(config.get("server_url", "")).rstrip("/")
        self.username = str(config.get("username", ""))
        self.password = str(config.get("password", ""))
        self.account_id = str(config.get("account_id", ""))
        self.domain = str(config.get("domain", "default"))
        
        self.token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None

    def _get_headers(self) -> Dict[str, str]:
        """Builds standard DXtrade headers, injecting DXToken if authenticated."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"DXToken {self.token}"
        return headers

    async def authenticate(self) -> bool:
        """Performs a login request to verify credentials and obtain a session token [4]."""
        if aiohttp is None:
            logger.error("Authentication aborted: aiohttp library is unavailable.")
            return False

        login_url = f"{self.server_url}/api/auth/login"
        payload = {
            "username": self.username,
            "password": self.password,
            "domain": self.domain
        }

        try:
            async with aiohttp.ClientSession() as temp_session:
                async with temp_session.post(login_url, json=payload, headers={"Content-Type": "application/json"}) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.token = data.get("sessionToken") or data.get("token")
                        if self.token:
                            logger.info("DXtrade session token successfully generated for User %s.", self.username)
                            return True
                        else:
                            logger.error("DXtrade login returned 200 OK, but failed to resolve a sessionToken key.")
                            return False
                    else:
                        resp_text = await response.text()
                        logger.error("DXtrade login rejected (Status %s): %s", response.status, resp_text)
                        return False
        except Exception as e:
            logger.error("Exception occurred during DXtrade authentication handshake: %s", str(e))
            return False

    async def connect(self) -> bool:
        """Establishes an active ClientSession cached with the DXToken auth header [2]."""
        if aiohttp is None:
            logger.error("Connection aborted: aiohttp is not installed.")
            return False

        auth_ok = await self.authenticate()
        if not auth_ok:
            return False

        # Close old session if alive
        if self.session and not self.session.closed:
            await self.session.close()

        self.session = aiohttp.ClientSession(headers=self._get_headers())
        self.is_connected = True
        return True

    async def disconnect(self) -> bool:
        """Termigates the active session and posts a logout payload to the server."""
        if self.session and not self.session.closed:
            try:
                # Optional: Send a logout POST request to clean up server session
                logout_url = f"{self.server_url}/api/auth/logout"
                await self.session.post(logout_url)
            except Exception:
                pass
            await self.session.close()

        self.token = None
        self.is_connected = False
        logger.info("DXtrade session cleanly terminated.")
        return True

    async def check_connection(self) -> bool:
        """Verifies session validity by running a lightweight user profile query [2]."""
        if not self.is_connected or self.session is None or self.session.closed:
            return await self.connect()

        url = f"{self.server_url}/api/accounts"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return True
                else:
                    logger.warning("DXtrade ping check returned status %s. Triggering reconnect...", response.status)
                    self.is_connected = False
                    return await self.connect()
        except Exception as e:
            logger.error("DXtrade session ping failed: %s", str(e))
            self.is_connected = False
            return await self.connect()

    async def get_account_info(self) -> BrokerAccountInfo:
        """Queries account metrics."""
        if not self.is_connected or self.session is None:
            raise ConnectionError("DXtrade session is not connected.")

        url = f"{self.server_url}/api/accounts/{self.account_id}/metrics"
        async with self.session.get(url) as response:
            if response.status != 200:
                text = await response.text()
                raise ValueError(f"Failed to fetch DXtrade account metrics (Status {response.status}): {text}")
            
            data = await response.json()
            metrics = data.get("metrics", {})

            # Map fields to unified schema
            balance = float(metrics.get("balance", 0.0))
            equity = float(metrics.get("equity", balance))
            margin_used = float(metrics.get("marginUsed", 0.0))
            margin_free = float(metrics.get("marginFree", balance))
            margin_level = (equity / margin_used * 100.0) if margin_used > 0 else float("inf")

            return BrokerAccountInfo(
                account_id=self.account_id,
                balance=balance,
                equity=equity,
                margin_used=margin_used,
                margin_free=margin_free,
                leverage=float(metrics.get("leverage", 100.0)),
                currency=metrics.get("currency", "USD"),
                margin_level_pct=margin_level
            )

    async def get_positions(self) -> List[BrokerPosition]:
        """Queries open positions assigned to the account."""
        if not self.is_connected or self.session is None:
            raise ConnectionError("DXtrade session is not connected.")

        url = f"{self.server_url}/api/accounts/{self.account_id}/positions"
        async with self.session.get(url) as response:
            if response.status != 200:
                text = await response.text()
                logger.error("Failed to query open DXtrade positions (Status %s): %s", response.status, text)
                return []

            data = await response.json()
            raw_positions = data.get("positions", [])

            positions_list = []
            for pos in raw_positions:
                side = str(pos.get("side", "BUY")).upper()  # BUY or SELL
                
                positions_list.append(BrokerPosition(
                    position_id=str(pos.get("positionId")),
                    symbol=pos.get("symbol", ""),
                    direction=side,
                    volume=float(pos.get("quantity", 0.0)),
                    entry_price=float(pos.get("averagePrice", 0.0)),
                    current_price=float(pos.get("currentPrice", 0.0)),
                    stop_loss=float(pos.get("stopLoss", 0.0)) if pos.get("stopLoss") else None,
                    take_profit=float(pos.get("takeProfit", 0.0)) if pos.get("takeProfit") else None,
                    swap=float(pos.get("swap", 0.0)),
                    commission=float(pos.get("commission", 0.0)),
                    unrealized_pnl=float(pos.get("unrealizedPnl", 0.0))
                ))

            return positions_list

    async def get_symbols(self) -> List[str]:
        """Queries symbols available on the DXtrade server."""
        if not self.is_connected or self.session is None:
            raise ConnectionError("DXtrade session is not connected.")

        url = f"{self.server_url}/api/instruments"
        async with self.session.get(url) as response:
            if response.status != 200:
                return []
            data = await response.json()
            instruments = data.get("instruments", [])
            return [ins.get("symbol") for ins in instruments if ins.get("symbol")]

    async def execute_order(self, order_request: Dict[str, Any]) -> BrokerOrderResult:
        """Dispatches an order execution request to DXtrade REST endpoints."""
        if not self.is_connected or self.session is None:
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message="DXtrade session is not connected."
            )

        symbol = order_request.get("symbol", "")
        direction = order_request.get("direction", "BUY").upper()
        volume = float(order_request.get("volume", 0.0))
        order_type_str = order_request.get("order_type", "MARKET").upper()

        # DXtrade order request payload body
        order_payload = {
            "symbol": symbol.upper(),
            "side": direction,  # BUY or SELL
            "quantity": volume,
            "type": order_type_str,
            "timeInForce": "FOK",
        }

        # Setup standard price parameters for pending orders
        if order_type_str in ["LIMIT", "STOP"]:
            order_payload["price"] = float(order_request["price"])

        # Setup custom limits
        if order_request.get("stop_loss") is not None:
            order_payload["stopLoss"] = {"price": float(order_request["stop_loss"])}
        if order_request.get("take_profit") is not None:
            order_payload["takeProfit"] = {"price": float(order_request["take_profit"])}

        url = f"{self.server_url}/api/accounts/{self.account_id}/orders"
        
        try:
            async with self.session.post(url, json=order_payload) as response:
                resp_text = await response.text()
                data = json.loads(resp_text)

                if response.status not in [200, 201]:
                    return BrokerOrderResult(
                        order_id="",
                        success=False,
                        status="REJECTED",
                        error_message=f"Order rejected by DXtrade (Status {response.status}): {data.get('errorMessage', resp_text)}"
                    )

                # Parse order execution status
                order_id = str(data.get("orderId", ""))
                exec_status = data.get("status", "FILLED").upper()  # FILLED, REJECTED, etc.

                if exec_status == "REJECTED":
                    return BrokerOrderResult(
                        order_id=order_id,
                        success=False,
                        status="REJECTED",
                        error_message=f"Execution rejected. Reason: {data.get('rejectReason', 'Unknown')}"
                    )

                return BrokerOrderResult(
                    order_id=order_id,
                    success=True,
                    status=exec_status,
                    filled_price=float(data.get("executionPrice", order_request.get("price", 0.0))),
                    filled_volume=volume
                )

        except Exception as e:
            logger.error("Exception triggered during DXtrade order dispatch: %s", str(e))
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message=f"Exception triggered: {str(e)}"
            )
