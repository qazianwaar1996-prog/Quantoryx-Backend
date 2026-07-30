# plugins/__init__.py
"""
Quantoryx — Plugin and Strategy Marketplace Framework Package.

Exposes the extensible plugin interface and dynamic runtime managers [1].
"""

from plugins.framework import BasePlugin, PluginManager

__all__ = [
    "BasePlugin",
    "PluginManager",
]
