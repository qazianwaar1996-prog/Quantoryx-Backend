# news/__init__.py
"""
Quantoryx — Economic Calendar Package.

Exposes the centralized economic calendar and news blackout manager [1].
"""

from news.calendar import EconomicCalendar, NewsEvent

__all__ = [
    "EconomicCalendar",
    "NewsEvent",
]
