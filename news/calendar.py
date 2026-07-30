# news/calendar.py
"""
Quantoryx — Economic Calendar and News Blackout Module.

Tracks scheduled macroeconomic events and evaluates risk blackout windows 
to pause or adjust active strategy execution parameters [7].
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.logging_config import get_logger

logger = get_logger("news.calendar")


@dataclass
class NewsEvent:
    """Standardized representation of an economic calendar event."""
    event_id: str
    title: str          # e.g., "FOMC Interest Rate Decision", "Non-Farm Payrolls"
    currency: str       # e.g., "USD", "EUR"
    impact: str         # "HIGH", "MEDIUM", "LOW"
    timestamp: datetime
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None


class EconomicCalendar:
    """
    Manages macro news events and enforces trading blackout safety windows [7].
    """

    def __init__(self):
        # Map event_id (str) -> NewsEvent object
        self.events: Dict[str, NewsEvent] = {}

    def add_event(self, event: NewsEvent):
        """Registers a scheduled economic event [7]."""
        self.events[event.event_id] = event
        logger.debug("News Event registered: [%s] %s (%s)", event.impact, event.title, event.currency)

    def get_upcoming_events(
        self,
        current_time: datetime,
        lookahead_hours: int = 24,
        min_impact: str = "HIGH"
    ) -> List[NewsEvent]:
        """
        Retrieves scheduled events within an upcoming time window [7].
        """
        boundary_time = current_time + timedelta(hours=lookahead_hours)
        impact_levels = self._get_impact_hierarchy(min_impact)

        upcoming = []
        for event in self.events.values():
            if current_time <= event.timestamp <= boundary_time:
                if event.impact in impact_levels:
                    upcoming.append(event)

        # Sort chronologically
        upcoming.sort(key=lambda x: x.timestamp)
        return upcoming

    def is_in_blackout_window(
        self,
        current_time: datetime,
        symbol: str,
        pre_event_minutes: int = 30,
        post_event_minutes: int = 15,
        min_impact: str = "HIGH"
    ) -> Tuple[bool, Optional[NewsEvent]]:
        """
        Audits if a trading execution falls within a news blackout window [7].
        
        Returns:
            Tuple of:
                - bool: True if inside a blackout window, False if trade is safe.
                - Optional[NewsEvent]: The macro event causing the blackout.
        """
        # Parse currency dependencies from the asset ticker (e.g. "EURUSD" -> ["EUR", "USD"])
        currencies = [symbol[:3].upper(), symbol[3:6].upper()] if len(symbol) == 6 else [symbol.upper()]
        impact_levels = self._get_impact_hierarchy(min_impact)

        for event in self.events.values():
            if event.impact in impact_levels and event.currency in currencies:
                # Define the blackout window
                blackout_start = event.timestamp - timedelta(minutes=pre_event_minutes)
                blackout_end = event.timestamp + timedelta(minutes=post_event_minutes)

                if blackout_start <= current_time <= blackout_end:
                    logger.warning(
                        "Blackout Window Active: Trade on %s paused. Event '%s' (%s) scheduled at %s.",
                        symbol, event.title, event.currency, event.timestamp
                    )
                    return True, event

        return False, None

    # =====================================================================
    # SEEDING UTILITIES (Offline Research / Testing support)
    # =====================================================================

    def seed_cyclical_forex_news(self, start_date: datetime, days: int = 90):
        """
        Pre-populates high-impact scheduled events (such as FOMC, NFP, CPI)
        chronologically to support backtests and offline validations [1, 7].
        """
        logger.info("Seeding scheduled macroeconomic event calendar for %s days...", days)
        current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = current_date + timedelta(days=days)

        event_index = 1
        while current_date < end_date:
            # 1. Non-Farm Payrolls (NFP) - First Friday of each month at 13:30 UTC
            if current_date.weekday() == 4 and 1 <= current_date.day <= 7:
                nfp_time = current_date.replace(hour=13, minute=30)
                self.add_event(NewsEvent(
                    event_id=f"news-nfp-{event_index}",
                    title="US Non-Farm Payrolls & Unemployment Rate",
                    currency="USD",
                    impact="HIGH",
                    timestamp=nfp_time
                ))
                event_index += 1

            # 2. FOMC Interest Rate Decisions - Cyclical Wednesday at 19:00 UTC (every 6 weeks)
            if current_date.weekday() == 2 and current_date.day in [10, 11, 12, 24, 25, 26]:
                fomc_time = current_date.replace(hour=19, minute=0)
                self.add_event(NewsEvent(
                    event_id=f"news-fomc-{event_index}",
                    title="FOMC Interest Rate Decision & Statement",
                    currency="USD",
                    impact="HIGH",
                    timestamp=fomc_time
                ))
                event_index += 1

            # 3. Consumer Price Index (CPI) - Standard Monthly release around the 12th day at 12:30 UTC
            if current_date.day == 12:
                # Map to closest business day (Mon-Fri)
                cpi_day = current_date
                if cpi_day.weekday() == 5:    # Saturday -> Friday
                    cpi_day -= timedelta(days=1)
                elif cpi_day.weekday() == 6:  # Sunday -> Monday
                    cpi_day += timedelta(days=1)
                
                cpi_time = cpi_day.replace(hour=12, minute=30)
                self.add_event(NewsEvent(
                    event_id=f"news-cpi-{event_index}",
                    title="US Consumer Price Index (YoY & MoM)",
                    currency="USD",
                    impact="HIGH",
                    timestamp=cpi_time
                ))
                event_index += 1

            # 4. ECB Interest Rate Decisions - standard monthly release at 12:15 UTC
            if current_date.day == 15 and current_date.weekday() < 5:
                ecb_time = current_date.replace(hour=12, minute=15)
                self.add_event(NewsEvent(
                    event_id=f"news-ecb-{event_index}",
                    title="ECB Interest Rate Decision",
                    currency="EUR",
                    impact="HIGH",
                    timestamp=ecb_time
                ))
                event_index += 1

            current_date += timedelta(days=1)

    @staticmethod
    def _get_impact_hierarchy(min_impact: str) -> List[str]:
        """Resolves target levels to check based on minimal impact filters."""
        impact_map = {
            "LOW": ["LOW", "MEDIUM", "HIGH"],
            "MEDIUM": ["MEDIUM", "HIGH"],
            "HIGH": ["HIGH"]
        }
        return impact_map.get(min_impact.upper(), ["HIGH"])
