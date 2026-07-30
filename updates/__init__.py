# updates/__init__.py
"""
Quantoryx — Auto Update Service Package.

Exposes the centralized desktop version check and transactional rollback update services [1].
"""

from updates.service import DesktopUpdateService, UpdateManifest

__all__ = [
    "DesktopUpdateService",
    "UpdateManifest",
]
