# licensing/__init__.py
"""
Quantoryx — Licensing and Subscription System Package.

Exposes the centralized licensing managers and structural metadata schemas [1].
"""

from licensing.manager import LicensingManager, LicenseMetadata

__all__ = [
    "LicensingManager",
    "LicenseMetadata",
]
