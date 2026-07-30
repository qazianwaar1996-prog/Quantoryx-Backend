# brokers/pepperstone_adapter.py
"""
Quantoryx — Pepperstone REST Broker Adapter.

Adapts Pepperstone API Gateway REST operations into the BaseBroker interface contract.
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

logger = get_logger("brokers.pepperstone")

# Defensive import to handle environments missing aiohttp cleanly [4]
try:
    import aiohttp
except ImportError:
    aiohttp = None
    logger.warning("aiohttp library is missing. Install it to activate the Pepperstone broker adapter.")


class PepperstoneAdapter(BaseBroker):
    """
    Pepperstone Broker Interface Adapter.
    Communicates via institutional REST endpoints using OAuth2 token authentication [4].
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the Pepperstone adapter.
        
        Expected Config Parameters:
            - api_key: str (Personal API Key)
            - api_secret: str (Personal API Secret / Password)
            - account_id: str (Account identifier)
            - environment: str ("demo" or "live", defaults to "demo")
        """
        super().__init__(broker_name="Pepperstone", config=config)
        self.api_key = str(config.get("api_key", ""))
        self.api_secret = str(config.get("api_secret", ""))
        self.account_id = str(config.get("account_id", ""))
        self.environment = str(config.get("environment", "demo")).lower()

        # Resolve REST API endpoints
        if self.environment == "live":
            self.base_url = "https://api.pepperstone.com/v1"
        else:
            self.base_url = "https://api.demo.pepperstone.com/v1"

        self.token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None

    def _get_headers(self) -> Dict[str, str]:
        """Builds standard authorization headers, injecting Bearer token if active."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def authenticate(self) -> bool:
        """Exchanges API key/secret credentials for a secure access token [4]."""
        if aiohttp is None:
            logger.error("Authentication aborted: aiohttp library is unavailable.")
            return False

        auth_url = f"{self.base_url}/oauth/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.api_secret
        }

        try:
            async with aiohttp.ClientSession() as temp_session:
                async with temp_session.post(auth_url, json=payload, headers={"Content-Type": "application/json"}) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.token = data.get("access_token")
                        if self.token:
                            logger.info("Pepperstone session token successfully established.")
                            return True
                        else:
                            logger.error("Pepperstone login succeeded, but response body lacks an 'access_token' key.")
                            return False
                    else:
                        resp_text = await response.text()
                        logger.error("Pepperstone token exchange rejected (Status %s): %s", response.status, resp_text)
                        return False
        except Exception as e:
            logger.error("Exception triggered during Pepperstone authentication: %s", str(e))
            return False

    async def connect(self) -> bool:
        """Establishes an active, token-cached ClientSession for REST execution [2]."""
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
        """Cleanly closes active client sessions."""
        if self.session and not self.session.closed:
            await self.session.close()
        self.token = None
        self.is_connected = False
        logger.info("Pepperstone REST session cleanly terminated.")
        return True

    async def check_connection(self) -> bool:
        """Checks connection health by querying the summary endpoint [2]."""
        if not self.is_connected or self.session is None or self.session.closed:
            return await self.connect()

        url = f"{self.base_url}/accounts/{self.account_id}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return True
                else:
                    logger.warning("Pepperstone connection ping returned status %s. Reconnecting...", response.status)
                    self.is_connected = False
                    return await self.connect()
        except Exception as e:
            logger.error("Pepperstone connection check crashed: %s", str(e))
            self.is_connected = False
            return await self.connect()

    async def get_account_info(self) -> BrokerAccountInfo:
        """Queries current balance and margin metrics."""
        if not self.is_connected or self.session is None:
            raise ConnectionError("Pepperstone REST session is not connected.")

        url = f"{self.base_url}/accounts/{self.account_id}"
        async with self.session.get(url) as response:
            if response.status != 200:
                text = await response.text()
                raise ValueError(f"Failed to fetch Pepperstone account summary (Status {response.status}): {text}")
            
            data = await response.json()
            summary = data.get("account", {})

            # Map fields to unified schema
            balance = float(summary.get("balance", 0.0))
            equity = float(summary.get("equity", balance))
            margin_used = float(summary.get("margin", 0.0))
            margin_free = float(summary.get("freeMargin", balance))
            margin_level = (equity / margin_used * 100.0) if margin_used > 0 else float("inf")

            return BrokerAccountInfo(
                account_id=self.account_id,
                balance=balance,
                equity=equity,
                margin_used=margin_used,
                margin_free=margin_free,
                leverage=float(summary.get("leverage", 100.0)),
                currency=summary.get("currency", "USD"),
                margin_level_pct=margin_level
            )

    async def get_positions(self) -> List[BrokerPosition]:
        """Queries currently active open positions."""
        if not self.is_connected or self.session is None:
            raise ConnectionError("Pepperstone REST session is not connected.")

        url = f"{self.base_url}/accounts/{self.account_id}/positions"
        async with self.session.get(url) as response:
            if response.status != 200:
                text = await response.text()
                logger.error("Failed to query open Pepperstone positions (Status %s): %s", response.status, text)
                return []

            data = await response.json()
            raw_positions = data.get("positions", [])

            positions_list = []
            for pos in raw_positions:
                side = str(pos.get("side", "BUY")).upper()
                
                positions_list.append(BrokerPosition(
                    position_id=str(pos.get("id")),
                    symbol=pos.get("symbol", ""),
                    direction=side,
                    volume=float(pos.get("quantity", 0.0)),
                    entry_price=float(pos.get("entryPrice", 0.0)),
                    current_price=float(pos.get("currentPrice", 0.0)),
                    stop_loss=float(pos.get("stopLoss", 0.0)) if pos.get("stopLoss") else None,
                    take_profit=float(pos.get("takeProfit", 0.0)) if pos.get("takeProfit") else None,
                    unrealized_pnl=float(pos.get("unrealizedPnl", 0.0))
                ))

            return positions_list

    async def get_symbols(self) -> List[str]:
        """Queries tradable symbols supported by the server."""
        if not self.is_connected or self.session is None:
            raise ConnectionError("Pepperstone REST session is not connected.")

        url = f"{self.base_url}/symbols"
        async with self.session.get(url) as response:
            if response.status != 200:
                return []
            data = await response.json()
            symbols = data.get("symbols", [])
            return [sym.get("name") for sym in symbols if sym.get("name")]

    async def execute_order(self, order_request: Dict[str, Any]) -> BrokerOrderResult:
        """Dispatches an order execution request to Pepperstone endpoints."""
        if not self.is_connected or self.session is None:
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message="Pepperstone REST session is not connected."
            )

        symbol = order_request.get("symbol", "")
        direction = order_request.get("direction", "BUY").upper()
        volume = float(order_request.get("volume", 0.0))
        order_type_str = order_request.get("order_type", "MARKET").upper()

        order_payload = {
            "symbol": symbol.upper(),
            "side": direction,
            "quantity": volume,
            "type": order_type_str,
            "timeInForce": "FOK"
        }

        # Setup standard price limits
        if order_type_str in ["LIMIT", "STOP"]:
            order_payload["price"] = float(order_request["price"])

        # Setup stop-loss/take-profit settings
        if order_request.get("stop_loss") is not None:
            order_payload["stopLoss"] = float(order_request["stop_loss"])
        if order_request.get("take_profit") is not None:
            order_payload["takeProfit"] = float(order_request["take_profit"])

        url = f"{self.base_url}/accounts/{self.account_id}/orders"
        
        try:
            async with self.session.post(url, json=order_payload) as response:
                resp_text = await response.text()
                data = json.loads(resp_text)

                if response.status not in [200, 201]:
                    return BrokerOrderResult(
                        order_id="",
                        success=False,
                        status="REJECTED",
                        error_message=f"Order rejected by Pepperstone (Status {response.status}): {data.get('errorMessage', resp_text)}"
                    )

                order_id = str(data.get("orderId", ""))
                exec_status = data.get("status", "FILLED").upper()

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
            logger.error("Exception triggered during Pepperstone order execution: %s", str(e))
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message=f"Exception triggered: {str(e)}"
            )
