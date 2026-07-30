# cloud/sync.py
"""
Quantoryx — Provider-Agnostic Cloud Synchronization Layer.

Establishes the BaseCloudStorageAdapter interface and a CloudSyncCoordinator 
to synchronize strategies, watchlists, and user preferences cleanly [11].
"""

import os
import sys
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.logging_config import get_logger

logger = get_logger("cloud.sync")


class BaseCloudStorageAdapter(ABC):
    """
    Abstract contract for cloud storage engines (AWS S3, GCP, Azure, custom self-hosted REST) [11].
    Ensures the sync coordinator is completely decoupled from cloud-specific vendor APIs [11].
    """

    @abstractmethod
    async def upload_json(self, bucket: str, key: str, data: Dict[str, Any]) -> bool:
        """
        Serializes and uploads a JSON-compatible dictionary to the cloud gateway [11].
        """
        pass

    @abstractmethod
    async def download_json(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """
        Downloads and parses a JSON-compatible file from the cloud gateway [11].
        """
        pass

    @abstractmethod
    async def delete_object(self, bucket: str, key: str) -> bool:
        """
        Deletes a target object from the cloud gateway [11].
        """
        pass


class CloudSyncCoordinator:
    """
    Coordinates multi-asset and multi-user configuration synchronizations [11].
    Utilizes dependency injection to remain completely storage provider agnostic [11].
    """

    def __init__(self, storage_adapter: BaseCloudStorageAdapter, bucket_name: str = "quantoryx-sync"):
        """
        Parameters:
            storage_adapter: An active instance subclassing BaseCloudStorageAdapter.
            bucket_name: Target cloud storage container namespace [11].
        """
        self.adapter = storage_adapter
        self.bucket = bucket_name

    # =====================================================================
    # COORDINATED USER SNAPSHOT SYNCHRONIZATIONS (Async)
    # =====================================================================

    async def sync_strategy_configurations(self, user_id: str, strategies_data: Dict[str, Any]) -> bool:
        """Uploads and syncs strategy configs to the user's cloud path [11]."""
        key = f"users/{user_id}/strategies.json"
        logger.info("Cloud Sync: Uploading strategy parameters for User %s...", user_id)
        return await self.adapter.upload_json(self.bucket, key, strategies_data)

    async def download_strategy_configurations(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Downloads the synced strategy configuration history [11]."""
        key = f"users/{user_id}/strategies.json"
        return await self.adapter.download_json(self.bucket, key)

    async def sync_watchlist_selections(self, user_id: str, watchlists_data: List[Dict[str, Any]]) -> bool:
        """Uploads and syncs user-customized watchlist settings [11]."""
        key = f"users/{user_id}/watchlists.json"
        logger.info("Cloud Sync: Uploading watchlist configurations for User %s...", user_id)
        # Wrap the list in a standard dictionary for storage consistency
        payload = {"watchlists": watchlists_data}
        return await self.adapter.upload_json(self.bucket, key, payload)

    async def download_watchlist_selections(self, user_id: str) -> Optional[List[Dict[str, Any]]]:
        """Downloads the synced watchlist configuration history [11]."""
        key = f"users/{user_id}/watchlists.json"
        data = await self.adapter.download_json(self.bucket, key)
        if data:
            return data.get("watchlists", [])
        return None

    async def sync_portfolio_metrics(self, user_id: str, portfolio_data: Dict[str, Any]) -> bool:
        """Uploads and syncs portfolio metrics and balance curves [11]."""
        key = f"users/{user_id}/portfolio.json"
        logger.info("Cloud Sync: Uploading portfolio curve snapshots for User %s...", user_id)
        return await self.adapter.upload_json(self.bucket, key, portfolio_data)

    async def download_portfolio_metrics(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Downloads the synced portfolio history [11]."""
        key = f"users/{user_id}/portfolio.json"
        return await self.adapter.download_json(self.bucket, key)

    async def sync_user_preferences(self, user_id: str, preferences_data: Dict[str, Any]) -> bool:
        """Uploads and syncs general user profile configurations and risk levels [11]."""
        key = f"users/{user_id}/preferences.json"
        logger.info("Cloud Sync: Uploading default preferences for User %s...", user_id)
        return await self.adapter.upload_json(self.bucket, key, preferences_data)

    async def download_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Downloads the synced user preference history [11]."""
        key = f"users/{user_id}/preferences.json"
        return await self.adapter.download_json(self.bucket, key)

    async def sync_dashboard_layout(self, user_id: str, layout_data: Dict[str, Any]) -> bool:
        """Uploads and syncs the dashboard panels and themes configuration (light/dark) [11]."""
        key = f"users/{user_id}/dashboard_layout.json"
        logger.info("Cloud Sync: Uploading custom dashboard layout settings for User %s...", user_id)
        return await self.adapter.upload_json(self.bucket, key, layout_data)

    async def download_dashboard_layout(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Downloads the synced dashboard panels configuration [11]."""
        key = f"users/{user_id}/dashboard_layout.json"
        return await self.adapter.download_json(self.bucket, key)
