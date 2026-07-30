# cloud/__init__.py
"""
Quantoryx — Cloud Sync Layer Package.

Exposes the provider-agnostic storage adapters and configuration sync coordinators [1].
"""

from cloud.sync import BaseCloudStorageAdapter, CloudSyncCoordinator

__all__ = [
    "BaseCloudStorageAdapter",
    "CloudSyncCoordinator",
]
