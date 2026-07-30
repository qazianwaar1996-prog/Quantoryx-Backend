# market_data/__init__.py
"""
Quantoryx — Market Data Layer Package.

Exposes unified data contracts, registers compiled data provider classes,
and provides a factory interface to instantiate pricing connections dynamically [1].
"""

from market_data.base import BaseMarketDataProvider, MarketTick
from market_data.twelvedata_provider import TwelveDataProvider
from market_data.polygon_provider import PolygonProvider
from market_data.finnhub_provider import FinnhubProvider

# Standardized Market Data Provider Registry Map [1]
MARKET_DATA_REGISTRY = {
    "twelvedata": TwelveDataProvider,
    "twelve_data": TwelveDataProvider,
    "polygon": PolygonProvider,
    "polygon_io": PolygonProvider,
    "finnhub": FinnhubProvider,
    "finnhub_io": FinnhubProvider,
}


def get_market_provider(
    provider_name: str,
    api_key: str,
    cache_expiry_seconds: int = 300,
    **kwargs
) -> BaseMarketDataProvider:
    """
    Factory interface to dynamically resolve and instantiate a target market data provider client [1].
    
    Parameters:
        provider_name: Name of the market data provider (case-insensitive, e.g., 'TwelveData', 'Polygon')
        api_key: The API authorization token assigned by the provider.
        cache_expiry_seconds: Expiration window for cached historical OHLCV queries [2].
    """
    normalized_name = provider_name.lower().replace(" ", "_").replace("-", "_").replace(".", "_")
    
    if normalized_name not in MARKET_DATA_REGISTRY:
        available_options = sorted(list(set(MARKET_DATA_REGISTRY.keys())))
        raise ValueError(
            f"Market data provider '{provider_name}' is not registered under Quantoryx v5.0.\n"
            f"Available options are: {available_options}"
        )
        
    provider_class = MARKET_DATA_REGISTRY[normalized_name]
    return provider_class(api_key=api_key, cache_expiry_seconds=cache_expiry_seconds, **kwargs)


__all__ = [
    "BaseMarketDataProvider",
    "MarketTick",
    "TwelveDataProvider",
    "PolygonProvider",
    "FinnhubProvider",
    "MARKET_DATA_REGISTRY",
    "get_market_provider",
]
