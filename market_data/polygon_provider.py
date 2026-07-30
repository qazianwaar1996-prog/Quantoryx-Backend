# market_data/polygon_provider.py
"""
Quantoryx — Polygon.io Market Data Provider Adapter.

Implements historical aggregate queries over REST and secure real-time forex pricing ticks.
Includes automatic in-memory caching, exponential backoff retries, and symbol translations.
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
import pandas as pd

# Ensure project root is in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from market_data.base import BaseMarketDataProvider, MarketTick
from utils.logging_config import get_logger

logger = get_logger("market_data.polygon")

# Defensive imports [4]
try:
    import aiohttp
    import websockets
except ImportError:
    aiohttp = None
    websockets = None
    logger.warning("aiohttp and websockets are required for the Polygon provider adapter.")


class PolygonProvider(BaseMarketDataProvider):
    """
    Polygon.io Market Data Client.
    Fetches historical aggregates over REST and streams live pricing over WebSockets.
    """

    # Timeframe mapping to resolve multiplier and timespan parameters
    TIMEFRAME_MAP = {
        "M15": (15, "minute"),
        "M30": (30, "minute"),
        "1H": (1, "hour"),
        "H1": (1, "hour"),
        "4H": (4, "hour"),
        "H4": (4, "hour"),
        "1D": (1, "day"),
        "D1": (1, "day")
    }

    def __init__(self, api_key: str, cache_expiry_seconds: int = 300):
        super().__init__(provider_name="Polygon", api_key=api_key, cache_expiry_seconds=cache_expiry_seconds)
        self.rest_base_url = "https://api.polygon.io"
        self.ws_base_url = "wss://socket.polygon.io/forex"  # Dedicated forex socket channel
        
        # Caching structures [2]
        self._history_cache: Dict[Tuple[str, int, str, str, str], Tuple[float, pd.DataFrame]] = {}
        
        # WebSockets state management
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_read_task: Optional[asyncio.Task] = None
        self.callbacks: Dict[str, Callable[[MarketTick], Any]] = {}

    def _normalize_rest_symbol(self, symbol: str) -> str:
        """Translates standard EURUSD tickers to Polygon's REST representation (C:EURUSD)."""
        symbol_clean = symbol.replace("/", "").upper()
        if not symbol_clean.startswith("C:"):
            return f"C:{symbol_clean}"
        return symbol_clean

    def _normalize_ws_symbol(self, symbol: str) -> str:
        """Translates standard EURUSD tickers to Polygon's WebSocket subscription (C.EUR/USD)."""
        symbol_clean = symbol.replace("/", "").upper()
        if len(symbol_clean) == 6:
            return f"C.{symbol_clean[:3]}/{symbol_clean[3:]}"
        return f"C.{symbol_clean}"

    def _denormalize_ws_symbol(self, symbol: str) -> str:
        """Translates Polygon's C.EUR/USD back to standard EURUSD tickers."""
        # Removes "C." prefix and any inner slash
        return symbol.replace("C.", "").replace("/", "").upper()

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Retrieves and caches historical aggregate bars using backoff retries [2]."""
        if aiohttp is None:
            raise ImportError("aiohttp library is required to retrieve historical data.")

        tf_params = self.TIMEFRAME_MAP.get(timeframe.upper())
        if not tf_params:
            raise ValueError(f"Timeframe interval '{timeframe}' is not supported by Polygon.")

        multiplier, timespan = tf_params
        normalized_symbol = self._normalize_rest_symbol(symbol)
        
        start_str = start_time.strftime("%Y-%m-%d")
        end_str = end_time.strftime("%Y-%m-%d")

        # Check in-memory cache first [2]
        cache_key = (normalized_symbol, multiplier, timespan, start_str, end_str)
        now = asyncio.get_event_loop().time()
        
        if cache_key in self._history_cache:
            cached_at, cached_df = self._history_cache[cache_key]
            if now - cached_at < self.cache_expiry_seconds:
                logger.debug("Returning cached historical candles for %s %s.", symbol, timeframe)
                return cached_df

        # Fetch from REST with exponential backoff retries [2]
        url = f"{self.rest_base_url}/v2/aggs/ticker/{normalized_symbol}/range/{multiplier}/{timespan}/{start_str}/{end_str}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "apiKey": self.api_key
        }

        retries = 3
        backoff = 2.0
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                try:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if data.get("status") in ["ERROR", "NOT_FOUND"]:
                                raise ValueError(f"Polygon API Error: {data.get('error', 'Query rejected')}")
                                
                            raw_results = data.get("results", [])
                            if not raw_results:
                                return self._format_ohlcv_dataframe(pd.DataFrame())

                            # Convert results to dataframe
                            # Polygon agg columns: o=open, h=high, l=low, c=close, v=volume, t=timestamp (ms)
                            df = pd.DataFrame(raw_results)
                            df["datetime"] = pd.to_datetime(df["t"], unit="ms")
                            df.set_index("datetime", inplace=True)
                            
                            # Rename to standard schema
                            df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}, inplace=True)
                            
                            formatted_df = self._format_ohlcv_dataframe(df)
                            
                            # Cache result [2]
                            self._history_cache[cache_key] = (now, formatted_df)
                            return formatted_df
                            
                        elif response.status == 429:
                            logger.warning("Polygon API limit exceeded (HTTP 429). Retrying in %ss...", backoff)
                        else:
                            logger.warning("Polygon API returned HTTP %s on attempt %s. Retrying...", response.status, attempt + 1)
                            
                except Exception as e:
                    logger.error("REST connection exception triggered on attempt %s: %s", attempt + 1, str(e))
                    if attempt == retries - 1:
                        raise e

                await asyncio.sleep(backoff)
                backoff *= 2.0

        raise ConnectionError("Failed to retrieve historical aggregates from Polygon after multiple attempts.")

    async def subscribe_realtime_ticks(
        self,
        symbol: str,
        on_tick_callback: Callable[[MarketTick], Any]
    ) -> bool:
        """Connects to the forex stream, authenticates, and subscribes to currency ticks."""
        if websockets is None:
            raise ImportError("websockets library is required to stream real-time price ticks.")

        normalized_symbol = self._normalize_ws_symbol(symbol)
        self.callbacks[normalized_symbol] = on_tick_callback

        # Open socket connection if not currently active
        if self.ws is None or self.ws.closed:
            try:
                self.ws = await websockets.connect(self.ws_base_url)
                self.is_streaming = True
                self.ws_read_task = asyncio.create_task(self._socket_listener())
                logger.info("Opened secure WebSocket connection to Polygon forex gateway.")
            except Exception as e:
                logger.error("Failed to connect to Polygon WebSocket gateway: %s", str(e))
                self.is_streaming = False
                return False

        # If socket is newly initialized, the listener handles authentication.
        # Once authenticated, we submit the subscription request.
        if self.is_streaming:
            subscribe_payload = {
                "action": "subscribe",
                "params": normalized_symbol
            }
            await self.ws.send(json.dumps(subscribe_payload))
            logger.info("Subscription request dispatched to Polygon for: %s", symbol)
            return True
        return False

    async def unsubscribe_realtime_ticks(self, symbol: str) -> bool:
        """Cancels streaming subscription for a specified instrument."""
        normalized_symbol = self._normalize_ws_symbol(symbol)
        self.callbacks.pop(normalized_symbol, None)

        if self.ws and not self.ws.closed:
            unsubscribe_payload = {
                "action": "unsubscribe",
                "params": normalized_symbol
            }
            await self.ws.send(json.dumps(unsubscribe_payload))
            logger.info("Unsubscribed from Polygon real-time stream for symbol: %s", symbol)
            return True
        return False

    async def disconnect_streams(self) -> bool:
        """Cleanly terminates WebSocket pricing feeds."""
        self.is_streaming = False
        self.callbacks.clear()

        if self.ws_read_task and not self.ws_read_task.done():
            self.ws_read_task.cancel()
            try:
                await self.ws_read_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()

        logger.info("Polygon real-time streams cleanly disconnected.")
        return True

    async def check_provider_status(self) -> bool:
        """Confirms provider API status availability."""
        if aiohttp is None:
            return False
            
        url = f"{self.rest_base_url}/v2/aggs/ticker/C:EURUSD/range/1/day/2026-01-01/2026-01-02"
        params = {"apiKey": self.api_key}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("status") == "OK"
                    return False
        except Exception:
            return False

    # =====================================================================
    # INNER WEBSOCKET DISPATCHER LOOP
    # =====================================================================

    async def _socket_listener(self):
        """Asynchronously reads incoming ticker frames from the socket [2]."""
        try:
            while self.is_streaming and self.ws and not self.ws.closed:
                message = await self.ws.recv()
                records = json.loads(message)

                # Polygon returns messages as a list of event packets
                for data in records:
                    event_type = data.get("ev")

                    # Handle connection authentication prompt
                    if event_type == "status" and data.get("status") == "connected":
                        logger.info("WebSocket handshake successful. Sending authorization credentials...")
                        auth_payload = {
                            "action": "auth",
                            "params": self.api_key
                        }
                        await self.ws.send(json.dumps(auth_payload))

                    elif event_type == "status" and data.get("status") == "auth_success":
                        logger.info("Polygon WebSocket session authorized successfully.")
                        # Resubscribe to any registered symbols on reconnection
                        if self.callbacks:
                            symbols_to_subscribe = ",".join(self.callbacks.keys())
                            subscribe_payload = {
                                "action": "subscribe",
                                "params": symbols_to_subscribe
                            }
                            await self.ws.send(json.dumps(subscribe_payload))

                    # Process Quote events (ev='C' is forex tick quotes)
                    elif event_type == "C":
                        symbol_key = data.get("p")
                        callback = self.callbacks.get(symbol_key)
                        
                        if callback:
                            bid = float(data.get("b", 0.0))
                            ask = float(data.get("a", 0.0))
                            mid_price = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else bid
                            
                            tick = MarketTick(
                                symbol=self._denormalize_ws_symbol(symbol_key),
                                bid=bid,
                                ask=ask,
                                last_price=mid_price,
                                timestamp=datetime.utcfromtimestamp(data.get("t", datetime.utcnow().timestamp() * 1000) / 1000.0)
                            )
                            
                            # Trigger registered strategy/execution callback
                            if asyncio.iscoroutinefunction(callback):
                                await callback(tick)
                            else:
                                callback(tick)

                    # Handle other server state failures
                    elif event_type == "status" and data.get("status") == "error":
                        logger.error("Polygon WebSocket session error: %s", data.get("message"))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Polygon socket listener loop caught exception: %s", str(e))
            self.is_streaming = False
