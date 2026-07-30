# plugins/framework.py
"""
Quantoryx — Extensible Plugin and Strategy Marketplace Framework.

Provides base contracts and dynamic loading utilities to load, validate, 
version, and enable third-party trading strategy packages at runtime [13].
"""

import os
import sys
import importlib.util
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategies.base import BaseStrategy
from strategies import STRATEGY_REGISTRY
from utils.path_manager import PathManager
from utils.logging_config import get_logger

logger = get_logger("plugins.framework")


class BasePlugin(ABC):
    """
    Abstract Base Class establishing the contract for marketplace plugins.
    Every custom strategy package must implement these properties and lifecycles [13].
    """

    def __init__(self):
        self.is_enabled = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique, lower-case identifier for the plugin (e.g., 'mean_reversion_pro')."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string of the plugin package (e.g., '1.0.2')."""
        pass

    @property
    @abstractmethod
    def author(self) -> str:
        """Author or developmental entity branding string."""
        pass

    @property
    @abstractmethod
    def strategy_class(self) -> Type[BaseStrategy]:
        """Returns the concrete strategy class implementing BaseStrategy [13]."""
        pass

    @abstractmethod
    def initialize(self) -> bool:
        """
        Runs custom startup configurations, caching setups, or licensing checks.
        Returns True if successful, False if startup aborted [13].
        """
        pass

    @abstractmethod
    def shutdown(self) -> bool:
        """
        Cleanly closes any open resources, thread-pools, or sockets upon disablement.
        """
        pass


class PluginManager:
    """
    Orchestrates the discovery, dynamic loading, and validation of custom plugins [13].
    """

    def __init__(self, plugins_dir_name: str = "plugins_installed"):
        # Resolve path using PathManager
        self.plugins_dir = PathManager.resolve_path("output", plugins_dir_name)
        os.makedirs(self.plugins_dir, exist_ok=True)
        
        # Map plugin_name (str) -> BasePlugin instance
        self.loaded_plugins: Dict[str, BasePlugin] = {}

    def discover_and_load_plugins(self) -> List[str]:
        """
        Scans the designated folder for custom Python modules and loads them [13].
        """
        loaded_names = []
        if not os.path.exists(self.plugins_dir):
            return []

        logger.info("Scanning directory '%s' for custom marketplace strategy plugins...", self.plugins_dir)
        
        for file in os.listdir(self.plugins_dir):
            if file.endswith(".py") and not file.startswith("__"):
                filepath = os.path.join(self.plugins_dir, file)
                plugin_name = file[:-3]
                
                try:
                    plugin_instance = self._load_plugin_module(plugin_name, filepath)
                    if plugin_instance:
                        self.loaded_plugins[plugin_instance.name] = plugin_instance
                        loaded_names.append(plugin_instance.name)
                        logger.info("Marketplace Plugin loaded: %s v%s by %s", plugin_instance.name, plugin_instance.version, plugin_instance.author)
                except Exception as e:
                    logger.error("Failed to dynamically load plugin file '%s': %s", file, str(e), exc_info=True)

        return loaded_names

    def enable_plugin(self, plugin_name: str) -> bool:
        """
        Initializes and registers a plugin's strategy into the core engine mapping [13, 15].
        """
        plugin = self.loaded_plugins.get(plugin_name.lower())
        if not plugin:
            logger.warning("Enable rejected: Plugin '%s' is not loaded.", plugin_name)
            return False

        if plugin.is_enabled:
            logger.debug("Plugin '%s' is already active.", plugin_name)
            return True

        # Initialize the plugin first
        try:
            initialized = plugin.initialize()
            if not initialized:
                logger.error("Enable aborted: Plugin '%s' failed to initialize.", plugin_name)
                return False

            # Inject the strategy class into the global STRATEGY_REGISTRY [13, 15]
            strategy_cls = plugin.strategy_class
            strategy_key = plugin.name.lower()
            
            # Map into core strategy registry map
            STRATEGY_REGISTRY[strategy_key] = strategy_cls
            
            plugin.is_enabled = True
            logger.info("Marketplace Strategy '%s' has been initialized and registered into the core engine [13, 15].", strategy_key)
            return True

        except Exception as e:
            logger.error("Error occurred while enabling plugin '%s': %s", plugin_name, str(e))
            return False

    def disable_plugin(self, plugin_name: str) -> bool:
        """
        Shuts down and unregisters a marketplace strategy plugin from the core registry [13, 15].
        """
        plugin = self.loaded_plugins.get(plugin_name.lower())
        if not plugin or not plugin.is_enabled:
            return False

        try:
            # Shut down plugin resources
            plugin.shutdown()
            
            # Remove from core strategies registry [13, 15]
            strategy_key = plugin.name.lower()
            STRATEGY_REGISTRY.pop(strategy_key, None)
            
            plugin.is_enabled = False
            logger.info("Marketplace Strategy '%s' has been unregistered and disabled.", strategy_key)
            return True
        except Exception as e:
            logger.error("Error occurred while disabling plugin '%s': %s", plugin_name, str(e))
            return False

    # =====================================================================
    # DYNAMIC RUNTIME IMPORT UTILITIES
    # =====================================================================

    def _load_plugin_module(self, module_name: str, filepath: str) -> Optional[BasePlugin]:
        """
        Performs low-level file loading to compile Python source into a modules scope [13].
        """
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Iterate over module variables to find the subclass of BasePlugin
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type) and 
                issubclass(attr, BasePlugin) and 
                attr is not BasePlugin
            ):
                # Instantiate and validate the plugin contract [13]
                plugin_instance = attr()
                self._validate_plugin_instance(plugin_instance)
                return plugin_instance

        return None

    def _validate_plugin_instance(self, plugin: BasePlugin):
        """
        Ensures the loaded plugin instance is compliant [13].
        """
        if not plugin.name:
            raise ValueError("Plugin validation failed: 'name' property is undefined.")
        if not plugin.version:
            raise ValueError("Plugin validation failed: 'version' property is undefined.")
        if not plugin.strategy_class or not issubclass(plugin.strategy_class, BaseStrategy):
            raise ValueError("Plugin validation failed: 'strategy_class' must subclass BaseStrategy.")
