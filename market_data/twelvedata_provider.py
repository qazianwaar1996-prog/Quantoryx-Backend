# market_data/twelvedata_provider.py
"""
Quantoryx — TwelveData Market Data Provider Adapter.

Implements historical candle retrieval and streaming WebSocket tick feeds [1, 2].
Features automated exponential backoff retries, in-memory caching, and symbol formatting [1, 2].
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

logger = get_logger("market_data.twelvedata")

# Defensive imports [4]
try:
    import aiohttp
    import websockets
except ImportError:
    aiohttp = None
    websockets = None
    logger.warning("aiohttp and websockets are required for the TwelveData provider adapter.")


class TwelveDataProvider(BaseMarketDataProvider):
    """
    TwelveData Market Data Client.
    Fetches historical OHLCV data over REST and streams pricing updates over secure WebSockets [2].
    """

    # Timeframe mapping dictionary to match TwelveData interval values
    TIMEFRAME_MAP = {
        "M15": "15min", "M30": "30min",
        "1H": "1h", "H1": "1h",
        "4H": "4h", "H4": "4h",
        "1D": "1day", "D1": "1day"
    }

    def __init__(self, api_key: str, cache_expiry_seconds: int = 300):
        super().__init__(provider_name="TwelveData", api_key=api_key, cache_expiry_seconds=cache_expiry_seconds)
        self.rest_base_url = "https://api.twelvedata.com"
        self.ws_base_url = "wss://ws.twelvedata.com/v1/quotes/price"
        
        # Caching structures [2]
        self._history_cache: Dict[Tuple[str, str, str, str], Tuple[float, pd.DataFrame]] = {}
        
        # WebSockets state management
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_read_task: Optional[asyncio.Task] = None
        self.callbacks: Dict[str, Callable[[MarketTick], Any]] = {}

    def _normalize_symbol(self, symbol: str) -> str:
        """Translates standard EURUSD tickers to TwelveData's EUR/USD representation."""
        if len(symbol) == 6 and "/" not in symbol:
            # Assume 6-character forex pairs require an inline slash
            return f"{symbol[:3]}/{symbol[3:]}"
        return symbol.upper()

    def _denormalize_symbol(self, symbol: str) -> str:
        """Translates TwelveData's EUR/USD back to standard EURUSD tickers."""
        return symbol.replace("/", "").upper()

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Retrieves and caches historical candles using defensive retry pipelines [2]."""
        if aiohttp is None:
            raise ImportError("aiohttp library is required to retrieve historical data.")

        interval = self.TIMEFRAME_MAP.get(timeframe.upper())
        if not interval:
            raise ValueError(f"Timeframe interval '{timeframe}' is not supported by TwelveData.")

        normalized_symbol = self._normalize_symbol(symbol)
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

        # Check in-memory cache first [2]
        cache_key = (normalized_symbol, interval, start_str, end_str)
        now = asyncio.get_event_loop().time()
        
        if cache_key in self._history_cache:
            cached_at, cached_df = self._history_cache[cache_key]
            if now - cached_at < self.cache_expiry_seconds:
                logger.debug("Returning cached historical candles for %s %s.", symbol, timeframe)
                return cached_df

        # Fetch from REST with exponential backoff retries [2]
        url = f"{self.rest_base_url}/time_series"
        params = {
            "symbol": normalized_symbol,
            "interval": interval,
            "start_date": start_str,
            "end_date": end_str,
            "apikey": self.api_key,
            "order": "ASC"
        }

        retries = 3
        backoff = 2.0
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                try:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Handle API-level parameter failures
                            if data.get("status") == "error":
                                raise ValueError(f"TwelveData API Error: {data.get('message')}")
                                
                            raw_values = data.get("values", [])
                            if not raw_values:
                                return self._format_ohlcv_dataframe(pd.DataFrame())

                            # Convert to dataframe
                            df = pd.DataFrame(raw_values)
                            df.set_index("datetime", inplace=True)
                            
                            # Standardize column headers and format types
                            formatted_df = self._format_ohlcv_dataframe(df)
                            
                            # Cache result [2]
                            self._history_cache[cache_key] = (now, formatted_df)
                            return formatted_df
                            
                        elif response.status == 429:
                            logger.warning("TwelveData API rate limit exceeded (HTTP 429). Retrying in %ss...", backoff)
                        else:
                            logger.warning("TwelveData API returned HTTP %s on attempt %s. Retrying...", response.status, attempt + 1)
                            
                except Exception as e:
                    logger.error("REST connection exception triggered on attempt %s: %s", attempt + 1, str(e))
                    if attempt == retries - 1:
                        raise e

                await asyncio.sleep(backoff)
                backoff *= 2.0

        raise ConnectionError("Failed to retrieve historical candles from TwelveData after multiple attempts.")

    async def subscribe_realtime_ticks(
        self,
        symbol: str,
        on_tick_callback: Callable[[MarketTick], Any]
    ) -> bool:
        """Establishes WebSocket pricing streams and registers tick listeners [1, 2]."""
        if websockets is None:
            raise ImportError("websockets library is required to stream real-time price ticks.")

        normalized_symbol = self._normalize_symbol(symbol)
        self.callbacks[normalized_symbol] = on_tick_callback

        # Open socket connection if not currently active
        if self.ws is None or self.ws.closed:
            ws_url = f"{self.ws_base_url}?apikey={self.api_key}"
            try:
                self.ws = await websockets.connect(ws_url)
                self.is_streaming = True
                self.ws_read_task = asyncio.create_task(self._socket_listener())
                logger.info("TwelveData secure WebSocket pricing stream opened successfully.")
            except Exception as e:
                logger.error("Failed to connect to TwelveData WebSocket gateway: %s", str(e))
                self.is_streaming = False
                return False

        # Dispatch subscription subscription frame
        subscribe_payload = {
            "action": "subscribe",
            "params": {
                "symbols": normalized_symbol
            }
        }
        await self.ws.send(json.dumps(subscribe_payload))
        logger.info("Subscribed to TwelveData real-time stream for symbol: %s", symbol)
        return True

    async def unsubscribe_realtime_ticks(self, symbol: str) -> bool:
        """Cancels streaming subscription for a specified instrument."""
        normalized_symbol = self._normalize_symbol(symbol)
        self.callbacks.pop(normalized_symbol, None)

        if self.ws and not self.ws.closed:
            unsubscribe_payload = {
                "action": "unsubscribe",
                "params": {
                    "symbols": normalized_symbol
                }
            }
            await self.ws.send(json.dumps(unsubscribe_payload))
            logger.info("Unsubscribed from TwelveData real-time stream for symbol: %s", symbol)
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

        logger.info("TwelveData real-time streams cleanly disconnected.")
        return True

    async def check_provider_status(self) -> bool:
        """Confirms provider API status availability."""
        if aiohttp is None:
            return False
            
        url = f"{self.rest_base_url}/time_series"
        params = {
            "symbol": "EUR/USD",
            "interval": "1day",
            "outputsize": 1,
            "apikey": self.api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("status") == "ok"
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
                data = json.loads(message)

                # Process quote ticks
                # TwelveData streaming quote payload: {"event": "price", "symbol": "EUR/USD", "price": 1.1025, ...}
                if data.get("event") == "price":
                    symbol_key = data.get("symbol")
                    callback = self.callbacks.get(symbol_key)
                    
                    if callback:
                        price = float(data.get("price", 0.0))
                        tick = MarketTick(
                            symbol=self._denormalize_symbol(symbol_key),
                            bid=price,  # TwelveData simple price websocket emits consolidated quote price
                            ask=price,
                            last_price=price,
                            timestamp=datetime.utcfromtimestamp(data.get("timestamp", datetime.utcnow().timestamp()))
                        )
                        
                        # Trigger registered strategy/execution callback
                        if asyncio.iscoroutinefunction(callback):
                            await callback(tick)
                        else:
                            callback(tick)

                # Handle service errors or rate limit messages
                elif data.get("status") == "error":
                    logger.error("TwelveData WebSocket error message received: %s", data.get("message"))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("TwelveData socket listener loop caught exception: %s", str(e))
            self.is_streaming = False
