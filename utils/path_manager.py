# utils/path_manager.py

import os
from typing import Dict, Any


class PathManager:
    """
    Central coordinator for system directory structures and file path resolution.
    Eliminates redundant folder-creation logic and ensures consistent file placement
    across local and production backtesting runs.
    """
    # Standard directory mapping
    DIRECTORIES = {
        "data": "data",
        "output": "output",
        "optimization": os.path.join("output", "optimization"),
        "trades": os.path.join("output", "trades"),
        "reports": "reports",
        "config_opt": os.path.join("config", "optimized"),
        "logs": "logs"
    }

    @classmethod
    def initialize_workspace(cls):
        """
        Creates all required framework directories safely on system startup.
        """
        for label, path in cls.DIRECTORIES.items():
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                print(f"[-] Warning: Failed to initialize workspace directory '{path}': {e}")

    @classmethod
    def resolve_path(cls, category: str, filename: str) -> str:
        """
        Dynamically returns the absolute or relative target path for a file 
        within its standardized folder category, creating directories on-demand.
        
        Parameters:
            category: Target folder label (e.g., 'optimization', 'reports', 'logs')
            filename: Target file name (e.g., 'portfolio_report.csv')
        """
        if category not in cls.DIRECTORIES:
            raise KeyError(
                f"Directory category '{category}' is not managed by PathManager. "
                f"Available categories: {list(cls.DIRECTORIES.keys())}"
            )
            
        target_dir = cls.DIRECTORIES[category]
        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, filename)

    @classmethod
    def check_data_exists(cls, filename: str) -> bool:
        """
        Convenience validator to verify historical data availability inside the data/ folder.
        """
        path = os.path.join(cls.DIRECTORIES["data"], filename)
        return os.path.exists(path) and os.path.getsize(path) > 0
