# brokers/oanda_adapter.py
"""
Quantoryx — OANDA v20 REST Broker Adapter.

Implements OANDA v20 API integration over non-blocking asynchronous HTTP sessions [1, 2].
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

logger = get_logger("brokers.oanda")

# Defensive import to handle any environments missing aiohttp cleanly [4]
try:
    import aiohttp
except ImportError:
    aiohttp = None
    logger.warning("aiohttp library is missing. Install it via pip to activate the OANDA broker adapter.")


class OANDAAdapter(BaseBroker):
    """
    OANDA v20 Broker Interface Adapter.
    Communicates via standard REST endpoints using JWT Bearer authentication [4].
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the OANDA adapter.
        
        Expected Config Parameters:
            - api_token: str (REST personal access token)
            - account_id: str (OANDA account ID formatted as XXX-XXX-XXXXXXX-XXX)
            - environment: str ("demo" or "live", defaults to "demo")
        """
        super().__init__(broker_name="OANDA", config=config)
        self.api_token = str(config.get("api_token", ""))
        self.account_id = str(config.get("account_id", ""))
        self.environment = str(config.get("environment", "demo")).lower()
        
        # Resolve base URL paths
        if self.environment == "live":
            self.base_url = "https://api-fxtrade.oanda.com/v3"
        else:
            self.base_url = "https://api-fxpractice.oanda.com/v3"

        self.session: Optional[aiohttp.ClientSession] = None

    def _get_headers(self) -> Dict[str, str]:
        """Builds standardized OANDA auth headers."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

    async def authenticate(self) -> bool:
        """Confirms access token validity by sending a lightweight account probe."""
        if aiohttp is None:
            logger.error("Authentication aborted: aiohttp library is unavailable.")
            return False

        headers = self._get_headers()
        url = f"{self.base_url}/accounts/{self.account_id}/summary"
        
        try:
            async with aiohttp.ClientSession() as temp_session:
                async with temp_session.get(url, headers=headers) as response:
                    if response.status == 200:
                        logger.info("OANDA authentication verified successfully for account %s.", self.account_id)
                        return True
                    else:
                        resp_text = await response.text()
                        logger.error("OANDA authentication rejected (Status %s): %s", response.status, resp_text)
                        return False
        except Exception as e:
            logger.error("Exception triggered during OANDA authentication handshake: %s", str(e))
            return False

    async def connect(self) -> bool:
        """Instantiates the persistent aiohttp ClientSession used for REST polling [2]."""
        if aiohttp is None:
            logger.error("Connection aborted: aiohttp is not installed.")
            return False

        auth_ok = await self.authenticate()
        if not auth_ok:
            return False

        # Close previous sessions if active
        if self.session and not self.session.closed:
            await self.session.close()

        self.session = aiohttp.ClientSession(headers=self._get_headers())
        self.is_connected = True
        return True

    async def disconnect(self) -> bool:
        """Closes the current ClientSession cleanly."""
        if self.session and not self.session.closed:
            await self.session.close()
        self.is_connected = False
        logger.info("OANDA REST session cleanly terminated.")
        return True

    async def check_connection(self) -> bool:
        """Verifies session health by querying the summary endpoint [2]."""
        if not self.is_connected or self.session is None or self.session.closed:
            return await self.connect()

        url = f"{self.base_url}/accounts/{self.account_id}/summary"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return True
                else:
                    logger.warning("OANDA connection check returned status %s. Reconnecting...", response.status)
                    self.is_connected = False
                    return await self.connect()
        except Exception as e:
            logger.error("OANDA session ping check crashed: %s", str(e))
            self.is_connected = False
            return await self.connect()

    async def get_account_info(self) -> BrokerAccountInfo:
        """Queries the account state summary."""
        if not self.is_connected or self.session is None:
            raise ConnectionError("OANDA session is not connected.")

        url = f"{self.base_url}/accounts/{self.account_id}/summary"
        async with self.session.get(url) as response:
            if response.status != 200:
                text = await response.text()
                raise ValueError(f"Failed to fetch OANDA account info (Status {response.status}): {text}")
            
            data = await response.json()
            summary = data.get("account", {})

            # Map metrics to standard schema
            margin_used = float(summary.get("marginUsed", 0.0))
            equity = float(summary.get("NAV", 0.0))
            margin_level = (equity / margin_used * 100.0) if margin_used > 0 else float("inf")

            return BrokerAccountInfo(
                account_id=summary.get("id", self.account_id),
                balance=float(summary.get("balance", 0.0)),
                equity=equity,
                margin_used=margin_used,
                margin_free=float(summary.get("marginAvailable", 0.0)),
                leverage=100.0 / float(summary.get("marginRate", 0.02)),  # marginRate 0.02 = 1:50 leverage
                currency=summary.get("currency", "USD"),
                margin_level_pct=margin_level
            )

    async def get_positions(self) -> List[BrokerPosition]:
        """
        Retrieves active open trades.
        To track exact transaction indices, we parse individual trades rather than
        the aggregated openPositions endpoints [1, 4].
        """
        if not self.is_connected or self.session is None:
            raise ConnectionError("OANDA session is not connected.")

        url = f"{self.base_url}/accounts/{self.account_id}/openTrades"
        async with self.session.get(url) as response:
            if response.status != 200:
                text = await response.text()
                logger.error("Failed to query open OANDA trades (Status %s): %s", response.status, text)
                return []

            data = await response.json()
            raw_trades = data.get("trades", [])

            positions_list = []
            for t in raw_trades:
                initial_units = float(t.get("initialUnits", 0.0))
                current_units = float(t.get("currentUnits", 0.0))
                
                # Positive initial units implies Buy, Negative implies Sell
                direction = "BUY" if initial_units > 0 else "SELL"

                positions_list.append(BrokerPosition(
                    position_id=str(t.get("id")),
                    symbol=t.get("instrument", ""),
                    direction=direction,
                    volume=abs(current_units),
                    entry_price=float(t.get("price", 0.0)),
                    current_price=float(t.get("currentPrice", 0.0)),
                    stop_loss=float(t.get("stopLossOrder", {}).get("price")) if t.get("stopLossOrder") else None,
                    take_profit=float(t.get("takeProfitOrder", {}).get("price")) if t.get("takeProfitOrder") else None,
                    unrealized_pnl=float(t.get("unrealizedPL", 0.0))
                ))

            return positions_list

    async def get_symbols(self) -> List[str]:
        """Queries instruments configured on the OANDA server."""
        if not self.is_connected or self.session is None:
            raise ConnectionError("OANDA session is not connected.")

        url = f"{self.base_url}/accounts/{self.account_id}/instruments"
        async with self.session.get(url) as response:
            if response.status != 200:
                return []
            data = await response.json()
            instruments = data.get("instruments", [])
            return [ins.get("name") for ins in instruments]

    async def execute_order(self, order_request: Dict[str, Any]) -> BrokerOrderResult:
        """Dispatches an order execution request to OANDA REST endpoints."""
        if not self.is_connected or self.session is None:
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message="OANDA session is not connected."
            )

        symbol = order_request.get("symbol", "")
        direction = order_request.get("direction", "BUY").upper()
        volume = float(order_request.get("volume", 0.0))
        order_type_str = order_request.get("order_type", "MARKET").upper()

        # OANDA represents Buy/Sell purely based on the sign of the units
        units = volume if direction == "BUY" else -volume

        # Construct order payload
        order_body = {
            "order": {
                "units": str(int(units)),
                "instrument": symbol.upper(),
                "timeInForce": "FOK",  # Fill or Kill
                "type": order_type_str,
                "positionFill": "DEFAULT"
            }
        }

        # Setup custom limits
        if order_request.get("stop_loss") is not None:
            order_body["order"]["stopLossOnFill"] = {"price": str(order_request["stop_loss"])}
        if order_request.get("take_profit") is not None:
            order_body["order"]["takeProfitOnFill"] = {"price": str(order_request["take_profit"])}

        url = f"{self.base_url}/accounts/{self.account_id}/orders"
        
        try:
            async with self.session.post(url, json=order_body) as response:
                resp_text = await response.text()
                data = json.loads(resp_text)

                if response.status not in [201, 200]:
                    return BrokerOrderResult(
                        order_id="",
                        success=False,
                        status="REJECTED",
                        error_message=f"Order rejected by OANDA (Status {response.status}): {data.get('errorMessage', resp_text)}"
                    )

                # Parse order fill transactions
                fill_transaction = data.get("orderFillTransaction")
                reject_transaction = data.get("orderRejectTransaction")

                if reject_transaction:
                    return BrokerOrderResult(
                        order_id="",
                        success=False,
                        status="REJECTED",
                        error_message=f"Order rejected on fill. Reason: {reject_transaction.get('rejectReason', 'Unknown')}"
                    )

                if fill_transaction:
                    return BrokerOrderResult(
                        order_id=str(fill_transaction.get("id")),
                        success=True,
                        status="FILLED",
                        filled_price=float(fill_transaction.get("price", 0.0)),
                        filled_volume=float(fill_transaction.get("units", 0.0))
                    )

                return BrokerOrderResult(
                    order_id="",
                    success=False,
                    status="PENDING",
                    error_message="Order placed, but fill transaction details are absent from response."
                )

        except Exception as e:
            logger.error("Exception triggered during OANDA order dispatch: %s", str(e))
            return BrokerOrderResult(
                order_id="",
                success=False,
                status="REJECTED",
                error_message=f"Exception triggered: {str(e)}"
            )
