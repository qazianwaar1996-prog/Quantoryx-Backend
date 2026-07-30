# market_data/base.py
"""
Quantoryx — Abstract Market Data Provider Base Interface.

Defines standard schemas for streaming price ticks, enforces dataframe 
formatting rules for historical candles, and establishes the abstract contract [1].
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
import pandas as pd


@dataclass
class MarketTick:
    """Standardized representation of a high-frequency real-time pricing update."""
    symbol: str
    bid: float
    ask: float
    last_price: float
    volume: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BaseMarketDataProvider(ABC):
    """
    Abstract Base Class establishing the standard interface for market data providers.
    All provider-specific adapters (e.g., TwelveData, Polygon) must implement these async handlers [1].
    """

    def __init__(self, provider_name: str, api_key: str, cache_expiry_seconds: int = 300):
        self.provider_name = provider_name
        self.api_key = api_key
        self.cache_expiry_seconds = cache_expiry_seconds
        self.is_streaming = False

    @abstractmethod
    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """
        Retrieves historical candle data for a specified instrument and timeframe [1].
        
        Returns:
            pd.DataFrame: A pandas DataFrame containing historical bar records.
            The returned frame must conform to the Quantoryx standard schema:
                - Index: pd.DatetimeIndex (sorted chronologically)
                - Columns: ['open', 'high', 'low', 'close', 'volume'] (strictly lower-case)
        """
        pass

    @abstractmethod
    async def subscribe_realtime_ticks(
        self,
        symbol: str,
        on_tick_callback: Callable[[MarketTick], Any]
    ) -> bool:
        """
        Establishes a WebSocket or high-frequency polling connection to stream
        real-time price updates for a specified instrument symbol [1].
        
        Parameters:
            symbol: Ticker symbol (e.g., "EURUSD")
            on_tick_callback: A non-blocking callback function/coroutine triggered 
                              whenever a fresh standard MarketTick is resolved.
        """
        pass

    @abstractmethod
    async def unsubscribe_realtime_ticks(self, symbol: str) -> bool:
        """
        Closes or unsubscribes the real-time pricing stream for a specified symbol [1].
        """
        pass

    @abstractmethod
    async def disconnect_streams(self) -> bool:
        """
        Terminates all active high-frequency websocket connection loops.
        """
        pass

    @abstractmethod
    async def check_provider_status(self) -> bool:
        """
        Performs a lightweight ping check to verify API key and gateway health.
        """
        pass

    # =====================================================================
    # DATA VALIDATION HELPERS (Quantoryx Frame Standards)
    # =====================================================================

    def _format_ohlcv_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Enforces Quantoryx standard format: lower-case column headers, sorted index.
        """
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        # Create a deep copy to prevent modifying client frames
        formatted_df = df.copy()

        # Convert headers to lowercase
        formatted_df.columns = [str(col).lower() for col in formatted_df.columns]

        # Enforce presence of standard columns
        required_cols = ["open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in formatted_df.columns:
                # Inject defensive default or NaN values if a required field is missing
                formatted_df[col] = float("nan")

        # Select only standard fields
        formatted_df = formatted_df[required_cols]

        # Ensure datetime index is parsed and sorted chronologically
        if not isinstance(formatted_df.index, pd.DatetimeIndex):
            formatted_df.index = pd.to_datetime(formatted_df.index)
        
        formatted_df.sort_index(inplace=True)
        return formatted_df
