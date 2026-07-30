# market_data/finnhub_provider.py
"""
Quantoryx — Finnhub.io Market Data Provider Adapter.

Implements historical forex candle queries over REST and secure real-time quote feeds [1, 2].
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

logger = get_logger("market_data.finnhub")

# Defensive imports [4]
try:
    import aiohttp
    import websockets
except ImportError:
    aiohttp = None
    websockets = None
    logger.warning("aiohttp and websockets are required for the Finnhub provider adapter.")


class FinnhubProvider(BaseMarketDataProvider):
    """
    Finnhub.io Market Data Client.
    Queries historical forex candle bars over REST and streams pricing quotes over WebSockets [2].
    """

    # Timeframe mapping to resolve Finnhub resolution parameters
    TIMEFRAME_MAP = {
        "M15": "15",
        "M30": "30",
        "1H": "60",
        "H1": "60",
        "4H": "60",  # Finnhub does not support 4H natively on free tiers; fallback to 60m
        "H4": "60",
        "1D": "D",
        "D1": "D"
    }

    def __init__(self, api_key: str, cache_expiry_seconds: int = 300):
        super().__init__(provider_name="Finnhub", api_key=api_key, cache_expiry_seconds=cache_expiry_seconds)
        self.rest_base_url = "https://finnhub.io/api/v1"
        self.ws_base_url = "wss://ws.finnhub.io"
        
        # Caching structures [2]
        self._history_cache: Dict[Tuple[str, str, int, int], Tuple[float, pd.DataFrame]] = {}
        
        # WebSockets state management
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_read_task: Optional[asyncio.Task] = None
        self.callbacks: Dict[str, Callable[[MarketTick], Any]] = {}

    def _normalize_symbol(self, symbol: str) -> str:
        """Translates standard EURUSD tickers to Finnhub's Forex representation (OANDA:EUR_USD)."""
        symbol_clean = symbol.replace("/", "").upper()
        if len(symbol_clean) == 6:
            return f"OANDA:{symbol_clean[:3]}_{symbol_clean[3:]}"
        return symbol_clean

    def _denormalize_symbol(self, symbol: str) -> str:
        """Translates Finnhub's OANDA:EUR_USD back to standard EURUSD tickers."""
        # Removes "OANDA:" prefix and any inner underscore
        return symbol.replace("OANDA:", "").replace("_", "").upper()

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

        resolution = self.TIMEFRAME_MAP.get(timeframe.upper())
        if not resolution:
            raise ValueError(f"Timeframe interval '{timeframe}' is not supported by Finnhub.")

        normalized_symbol = self._normalize_symbol(symbol)
        
        # Finnhub expects UNIX timestamps in integer seconds
        from_ts = int(start_time.timestamp())
        to_ts = int(end_time.timestamp())

        # Check in-memory cache first [2]
        cache_key = (normalized_symbol, resolution, from_ts, to_ts)
        now = asyncio.get_event_loop().time()
        
        if cache_key in self._history_cache:
            cached_at, cached_df = self._history_cache[cache_key]
            if now - cached_at < self.cache_expiry_seconds:
                logger.debug("Returning cached historical candles for %s %s.", symbol, timeframe)
                return cached_df

        # Fetch from REST with exponential backoff retries [2]
        url = f"{self.rest_base_url}/forex/candle"
        params = {
            "symbol": normalized_symbol,
            "resolution": resolution,
            "from": from_ts,
            "to": to_ts,
            "token": self.api_key
        }

        retries = 3
        backoff = 2.0
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                try:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            status_code = data.get("s", "no_data")
                            if status_code == "no_data":
                                return self._format_ohlcv_dataframe(pd.DataFrame())
                            elif status_code == "error":
                                raise ValueError(f"Finnhub API Error: {data.get('msg', 'Query rejected')}")

                            # Convert results to dataframe
                            # Finnhub response lists: o=open, h=high, l=low, c=close, v=volume, t=timestamp (seconds)
                            raw_data = {
                                "open": [float(val) for val in data.get("o", [])],
                                "high": [float(val) for val in data.get("h", [])],
                                "low": [float(val) for val in data.get("l", [])],
                                "close": [float(val) for val in data.get("c", [])],
                                "volume": [float(val) for val in data.get("v", [])],
                                "t": [int(val) for val in data.get("t", [])]
                            }

                            df = pd.DataFrame(raw_data)
                            df["datetime"] = pd.to_datetime(df["t"], unit="s")
                            df.set_index("datetime", inplace=True)
                            df.drop(columns=["t"], inplace=True)
                            
                            formatted_df = self._format_ohlcv_dataframe(df)
                            
                            # Cache result [2]
                            self._history_cache[cache_key] = (now, formatted_df)
                            return formatted_df
                            
                        elif response.status == 429:
                            logger.warning("Finnhub API rate limit exceeded (HTTP 429). Retrying in %ss...", backoff)
                        else:
                            logger.warning("Finnhub API returned HTTP %s on attempt %s. Retrying...", response.status, attempt + 1)
                            
                except Exception as e:
                    logger.error("REST connection exception triggered on attempt %s: %s", attempt + 1, str(e))
                    if attempt == retries - 1:
                        raise e

                await asyncio.sleep(backoff)
                backoff *= 2.0

        raise ConnectionError("Failed to retrieve historical candles from Finnhub after multiple attempts.")

    async def subscribe_realtime_ticks(
        self,
        symbol: str,
        on_tick_callback: Callable[[MarketTick], Any]
    ) -> bool:
        """Connects to the Finnhub stream and sends standard subscription payloads [1, 2]."""
        if websockets is None:
            raise ImportError("websockets library is required to stream real-time price ticks.")

        normalized_symbol = self._normalize_symbol(symbol)
        self.callbacks[normalized_symbol] = on_tick_callback

        # Open socket connection if not currently active
        if self.ws is None or self.ws.closed:
            ws_url = f"{self.ws_base_url}?token={self.api_key}"
            try:
                self.ws = await websockets.connect(ws_url)
                self.is_streaming = True
                self.ws_read_task = asyncio.create_task(self._socket_listener())
                logger.info("Opened secure WebSocket connection to Finnhub gateway.")
            except Exception as e:
                logger.error("Failed to connect to Finnhub WebSocket gateway: %s", str(e))
                self.is_streaming = False
                return False

        # Dispatch subscription payload
        subscribe_payload = {
            "type": "subscribe",
            "symbol": normalized_symbol
        }
        await self.ws.send(json.dumps(subscribe_payload))
        logger.info("Subscription request dispatched to Finnhub for: %s", symbol)
        return True

    async def unsubscribe_realtime_ticks(self, symbol: str) -> bool:
        """Cancels streaming subscription for a specified instrument."""
        normalized_symbol = self._normalize_symbol(symbol)
        self.callbacks.pop(normalized_symbol, None)

        if self.ws and not self.ws.closed:
            unsubscribe_payload = {
                "type": "unsubscribe",
                "symbol": normalized_symbol
            }
            await self.ws.send(json.dumps(unsubscribe_payload))
            logger.info("Unsubscribed from Finnhub real-time stream for symbol: %s", symbol)
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
            except asyncio.cancelled_error:
                pass

        if self.ws:
            await self.ws.close()

        logger.info("Finnhub real-time streams cleanly disconnected.")
        return True

    async def check_provider_status(self) -> bool:
        """Confirms provider API status availability."""
        if aiohttp is None:
            return False
            
        url = f"{self.rest_base_url}/forex/candle"
        params = {
            "symbol": "OANDA:EUR_USD",
            "resolution": "D",
            "from": int(datetime.utcnow().timestamp()) - 86400,
            "to": int(datetime.utcnow().timestamp()),
            "token": self.api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("s") in ["ok", "no_data"]
                    return False
        except Exception:
            return False

    # =====================================================================
    # INNER WEBSOCKET DISPATCHER LOOP
    # =====================================================================

    async def _socket_listener(self):
        """Asynchronously reads incoming trade ticker frames from the socket [2]."""
        try:
            while self.is_streaming and self.ws and not self.ws.closed:
                message = await self.ws.recv()
                data = json.loads(message)

                # Process Quote Trade updates
                # Finnhub payload: {"data": [{"p": 1.1025, "s": "OANDA:EUR_USD", "t": 1574345600000, "v": 100}], "type": "trade"}
                if data.get("type") == "trade":
                    trades = data.get("data", [])
                    for trade in trades:
                        symbol_key = trade.get("s")
                        callback = self.callbacks.get(symbol_key)
                        
                        if callback:
                            price = float(trade.get("p", 0.0))
                            tick = MarketTick(
                                symbol=self._denormalize_symbol(symbol_key),
                                bid=price,
                                ask=price,
                                last_price=price,
                                volume=float(trade.get("v", 0.0)),
                                timestamp=datetime.utcfromtimestamp(trade.get("t", datetime.utcnow().timestamp() * 1000) / 1000.0)
                            )
                            
                            # Trigger registered strategy/execution callback
                            if asyncio.iscoroutinefunction(callback):
                                await callback(tick)
                            else:
                                callback(tick)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Finnhub socket listener loop caught exception: %s", str(e))
            self.is_streaming = False
