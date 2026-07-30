# backend/services/portfolio_services.py
"""
Quantoryx — Portfolio, Watchlist, and Notification Service Module.

This module orchestrates real-time active position tracking, watchlist collections,
and user-directed risk notification channels.
"""

import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

# Ensure root is in path for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.database.connection import SessionLocal
from backend.models.models import ActivePosition, Watchlist, WatchlistItem, Notification
from backend.repositories.repositories import (
    position_repo,
    watchlist_repo,
    watchlist_item_repo,
    notification_repo,
    audit_repo,
)
from utils.logging_config import get_logger

# Initialize central logger
logger = get_logger("backend.services.portfolio")


class PortfolioService:
    """
    Coordinates relational state transitions for portfolio holdings,
    watchlists, and user notification boards.
    """

    # =====================================================================
    # ACTIVE HOLDINGS (OPEN POSITIONS) SERVICES
    # =====================================================================

    @classmethod
    def get_active_positions(cls, user_id: str, db: Session = None) -> List[ActivePosition]:
        """Retrieves persistent active holdings representing open transactions."""
        session = db if db is not None else SessionLocal()
        try:
            return position_repo.get_by_user(session, user_id=user_id)
        finally:
            if db is None:
                session.close()

    @classmethod
    def persist_open_position(
        cls,
        user_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        size: float,
        stop_loss: float,
        take_profit: float,
        required_margin: float,
        entry_regime: Optional[str] = None,
        db: Session = None
    ) -> Optional[ActivePosition]:
        """Saves a newly initiated transaction state directly to the holdings database."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            position_data = {
                "user_id": user_id,
                "symbol": symbol.upper(),
                "direction": direction.upper(),
                "entry_price": entry_price,
                "size": size,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "required_margin": required_margin,
                "entry_regime": entry_regime,
                "entry_time": datetime.utcnow()
            }
            
            position_obj = position_repo.create(session, obj_in=position_data)
            
            if standalone:
                session.commit()
                session.refresh(position_obj)

            logger.info("Persisted open position for User %s | Asset: %s %s", user_id, direction, symbol)
            return position_obj

        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to persist open position transaction: %s", str(e), exc_info=True)
            return None
        finally:
            if standalone:
                session.close()

    @classmethod
    def remove_closed_position(cls, user_id: str, position_id: int, db: Session = None) -> bool:
        """Removes a finalized transaction from active holdings database records."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            position_obj = position_repo.get(session, position_id)
            if not position_obj or position_obj.user_id != user_id:
                logger.warning("Closed position removal rejected: Position %s missing or unauthorized.", position_id)
                return False

            position_repo.remove(session, id=position_id)
            
            if standalone:
                session.commit()

            logger.info("Removed active position %s following transaction closure.", position_id)
            return True

        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to remove active position %s: %s", position_id, str(e))
            return False
        finally:
            if standalone:
                session.close()


    # =====================================================================
    # WATCHLIST SERVICES
    # =====================================================================

    @classmethod
    def get_watchlists_by_user(cls, user_id: str, db: Session = None) -> List[Watchlist]:
        """Retrieves watchlist groupings configured by a user."""
        session = db if db is not None else SessionLocal()
        try:
            return watchlist_repo.get_by_user(session, user_id=user_id)
        finally:
            if db is None:
                session.close()

    @classmethod
    def create_watchlist(cls, user_id: str, name: str, db: Session = None) -> Optional[Watchlist]:
        """Instantiates a new named watchlist grouping."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            watchlist_data = {
                "user_id": user_id,
                "name": name,
                "created_at": datetime.utcnow()
            }
            watchlist_obj = watchlist_repo.create(session, obj_in=watchlist_data)

            if standalone:
                session.commit()
                session.refresh(watchlist_obj)

            logger.info("Watchlist '%s' initialized for User %s", name, user_id)
            return watchlist_obj
        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to create watchlist: %s", str(e))
            return None
        finally:
            if standalone:
                session.close()

    @classmethod
    def delete_watchlist(cls, user_id: str, watchlist_id: int, db: Session = None) -> bool:
        """Deletes a designated watchlist grouping after confirming ownership."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            watchlist = watchlist_repo.get(session, watchlist_id)
            if not watchlist or watchlist.user_id != user_id:
                return False

            watchlist_repo.remove(session, id=watchlist_id)
            
            if standalone:
                session.commit()
            return True
        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to delete watchlist %s: %s", watchlist_id, str(e))
            return False
        finally:
            if standalone:
                session.close()

    @classmethod
    def add_symbol_to_watchlist(
        cls, 
        user_id: str, 
        watchlist_id: int, 
        symbol: str, 
        db: Session = None
    ) -> Optional[WatchlistItem]:
        """Appends a tracking symbol ticker into an authorized watchlist."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            watchlist = watchlist_repo.get(session, watchlist_id)
            if not watchlist or watchlist.user_id != user_id:
                logger.warning("Watchlist append rejected: Watchlist %s unauthorized or missing.", watchlist_id)
                return None

            # Prevent duplicate item tracking in the same watchlist
            items = watchlist_item_repo.get_by_watchlist(session, watchlist_id)
            if any(item.symbol.upper() == symbol.upper() for item in items):
                logger.debug("Symbol %s already tracked inside watchlist %s.", symbol, watchlist_id)
                return None

            item_data = {
                "watchlist_id": watchlist_id,
                "symbol": symbol.upper(),
                "created_at": datetime.utcnow()
            }
            item_obj = watchlist_item_repo.create(session, obj_in=item_data)

            if standalone:
                session.commit()
                session.refresh(item_obj)

            return item_obj
        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to append symbol %s to watchlist %s: %s", symbol, watchlist_id, str(e))
            return None
        finally:
            if standalone:
                session.close()

    @classmethod
    def remove_symbol_from_watchlist(
        cls, 
        user_id: str, 
        watchlist_id: int, 
        item_id: int, 
        db: Session = None
    ) -> bool:
        """Removes a symbol record from an authorized watchlist."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            watchlist = watchlist_repo.get(session, watchlist_id)
            if not watchlist or watchlist.user_id != user_id:
                return False

            item = watchlist_item_repo.get(session, item_id)
            if not item or item.watchlist_id != watchlist_id:
                return False

            watchlist_item_repo.remove(session, id=item_id)
            
            if standalone:
                session.commit()
            return True
        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to remove item %s from watchlist %s: %s", item_id, watchlist_id, str(e))
            return False
        finally:
            if standalone:
                session.close()


    # =====================================================================
    # NOTIFICATION SERVICES
    # =====================================================================

    @classmethod
    def get_notifications_by_user(
        cls, 
        user_id: str, 
        unread_only: bool = True, 
        db: Session = None
    ) -> List[Notification]:
        """Retrieves generated risk alert and warning notifications."""
        session = db if db is not None else SessionLocal()
        try:
            if unread_only:
                return notification_repo.get_unread_by_user(session, user_id=user_id)
            return notification_repo.get_all_by_user(session, user_id=user_id)
        finally:
            if db is None:
                session.close()

    @classmethod
    def dispatch_notification(
        cls, 
        user_id: str, 
        title: str, 
        message: str, 
        db: Session = None
    ) -> Optional[Notification]:
        """Dispatches an operational system alert or notification."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            notification_data = {
                "user_id": user_id,
                "title": title,
                "message": message,
                "is_read": False,
                "created_at": datetime.utcnow()
            }
            notification_obj = notification_repo.create(session, obj_in=notification_data)

            if standalone:
                session.commit()
                session.refresh(notification_obj)

            return notification_obj
        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to dispatch alert notification: %s", str(e))
            return None
        finally:
            if standalone:
                session.close()

    @classmethod
    def mark_notification_read(cls, user_id: str, notification_id: int, db: Session = None) -> bool:
        """Dismisses an authorized notification record."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            notification = notification_repo.get(session, notification_id)
            if not notification or notification.user_id != user_id:
                return False

            notification.is_read = True
            session.add(notification)

            if standalone:
                session.commit()
            else:
                # A caller-supplied session is committed by the request
                # boundary, but subsequent reads inside the same unit of work
                # must observe the change, so flush it now. Without this the
                # unread count stays stale until the transaction closes.
                session.flush()
            return True
        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to mark notification %s as read: %s", notification_id, str(e))
            return False
        finally:
            if standalone:
                session.close()

    @classmethod
    def dismiss_all_notifications(cls, user_id: str, db: Session = None) -> bool:
        """Dismisses all unread notification records for a user."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            unread = notification_repo.get_unread_by_user(session, user_id=user_id)
            for notice in unread:
                notice.is_read = True
                session.add(notice)

            if standalone:
                session.commit()
            else:
                # Flush so later reads in the same unit of work see the update.
                session.flush()
            return True
        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to dismiss notifications for user %s: %s", user_id, str(e))
            return False
        finally:
            if standalone:
                session.close()
