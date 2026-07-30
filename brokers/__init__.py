# brokers/__init__.py
"""
Quantoryx — Broker Integration Layer Package.

Exposes unified data contracts, registers compiled adapter classes, 
and provides a clean factory interface to load target broker sessions on-demand [1].
"""

from brokers.base import (
    BaseBroker,
    BrokerAccountInfo,
    BrokerPosition,
    BrokerOrderResult,
)
from brokers.mt5_adapter import MT5Adapter
from brokers.oanda_adapter import OANDAAdapter
from brokers.ctrader_adapter import CTraderAdapter
from brokers.dxtrade_adapter import DXtradeAdapter
from brokers.ib_adapter import IBAdapter
from brokers.pepperstone_adapter import PepperstoneAdapter

# Standardized Broker Registration Map [1]
BROKER_REGISTRY = {
    "metatrader5": MT5Adapter,
    "mt5": MT5Adapter,
    "icmarkets": MT5Adapter,          # IC Markets utilizes standard MT5 terminal connection
    "ic_markets": MT5Adapter,
    "oanda": OANDAAdapter,
    "ctrader": CTraderAdapter,
    "dxtrade": DXtradeAdapter,
    "interactive_brokers": IBAdapter,
    "ib": IBAdapter,
    "ibkr": IBAdapter,
    "pepperstone": PepperstoneAdapter,
}


def get_broker(broker_name: str, config: dict) -> BaseBroker:
    """
    Factory interface to dynamically resolve and instantiate a target broker adapter [1].
    
    Parameters:
        broker_name: Name of the broker (case-insensitive)
        config: Dictionary containing required authentication and server connection arguments.
    """
    normalized_name = broker_name.lower().replace(" ", "_").replace("-", "_")
    
    if normalized_name not in BROKER_REGISTRY:
        available_options = sorted(list(set(BROKER_REGISTRY.keys())))
        raise ValueError(
            f"Broker '{broker_name}' is not registered under Quantoryx v5.0.\n"
            f"Available options are: {available_options}"
        )
        
    adapter_class = BROKER_REGISTRY[normalized_name]
    return adapter_class(config=config)


__all__ = [
    "BaseBroker",
    "BrokerAccountInfo",
    "BrokerPosition",
    "BrokerOrderResult",
    "MT5Adapter",
    "OANDAAdapter",
    "CTraderAdapter",
    "DXtradeAdapter",
    "IBAdapter",
    "PepperstoneAdapter",
    "BROKER_REGISTRY",
    "get_broker",
]
