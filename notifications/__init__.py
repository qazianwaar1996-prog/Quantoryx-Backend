# notifications/__init__.py
"""
Quantoryx — Notification System Package.

Exposes the centralized asynchronous notification delivery dispatcher [1].
"""

from notifications.notifier import NotificationDispatcher

__all__ = [
    "NotificationDispatcher",
]
