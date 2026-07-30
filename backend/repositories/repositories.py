# backend/repositories/repositories.py
"""
Quantoryx — Concrete Repositories Module.

This module implements specific query helpers for each data model
under the Repository pattern, ensuring strict type safety and
decoupling raw SQL operations from service consumers.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.models.models import (
    User,
    UserSettings,
    SavedStrategy,
    SavedBacktest,
    SavedOptimization,
    SavedAIAnalysis,
    SavedReport,
    ActivePosition,
    Watchlist,
    WatchlistItem,
    Notification,
    AuditLog,
)
from backend.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository handling custom user queries."""

    def __init__(self):
        super().__init__(User)

    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        """Fetches a user profile matching a target username (case-insensitive)."""
        return db.query(User).filter(User.username.ilike(username)).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """Fetches a user profile matching a target email (case-insensitive)."""
        return db.query(User).filter(User.email.ilike(email)).first()


class UserSettingsRepository(BaseRepository[UserSettings]):
    """Repository handling user operational settings queries."""

    def __init__(self):
        super().__init__(UserSettings)

    def get_by_user_id(self, db: Session, user_id: str) -> Optional[UserSettings]:
        """Fetches operational configurations matching a target user ID."""
        return db.query(UserSettings).filter(UserSettings.user_id == user_id).first()


class SavedStrategyRepository(BaseRepository[SavedStrategy]):
    """Repository handling saved strategy configurations."""

    def __init__(self):
        super().__init__(SavedStrategy)

    def get_by_user(self, db: Session, user_id: str) -> List[SavedStrategy]:
        """Fetches all strategies configured by a target user."""
        return db.query(SavedStrategy).filter(SavedStrategy.user_id == user_id).all()

    def get_favorites_by_user(self, db: Session, user_id: str) -> List[SavedStrategy]:
        """Fetches favorite strategies designated by a target user."""
        return db.query(SavedStrategy).filter(
            SavedStrategy.user_id == user_id, 
            SavedStrategy.is_favorite == True
        ).all()


class SavedBacktestRepository(BaseRepository[SavedBacktest]):
    """Repository handling historical backtesting simulation outcomes."""

    def __init__(self):
        super().__init__(SavedBacktest)

    def get_by_user(self, db: Session, user_id: str) -> List[SavedBacktest]:
        """Fetches all backtest runs committed by a target user."""
        return db.query(SavedBacktest).filter(SavedBacktest.user_id == user_id).all()


class SavedOptimizationRepository(BaseRepository[SavedOptimization]):
    """Repository handling saved parameter optimization sweeps."""

    def __init__(self):
        super().__init__(SavedOptimization)

    def get_by_user(self, db: Session, user_id: str) -> List[SavedOptimization]:
        """Fetches all parameter sweep rankings saved by a target user."""
        return db.query(SavedOptimization).filter(SavedOptimization.user_id == user_id).all()


class SavedAIAnalysisRepository(BaseRepository[SavedAIAnalysis]):
    """Repository handling saved AI decision engine evaluations."""

    def __init__(self):
        super().__init__(SavedAIAnalysis)

    def get_by_user(self, db: Session, user_id: str) -> List[SavedAIAnalysis]:
        """Fetches all cognitive AI trace selections saved by a target user."""
        return db.query(SavedAIAnalysis).filter(SavedAIAnalysis.user_id == user_id).all()


class SavedReportRepository(BaseRepository[SavedReport]):
    """Repository handling compiled CSV report storage listings."""

    def __init__(self):
        super().__init__(SavedReport)

    def get_by_user(self, db: Session, user_id: str) -> List[SavedReport]:
        """Fetches all CSV output report entries linked to a target user."""
        return db.query(SavedReport).filter(SavedReport.user_id == user_id).all()


# =====================================================================
# v4.5 REPOSITORIES FOR NEW MODELS
# =====================================================================

class ActivePositionRepository(BaseRepository[ActivePosition]):
    """Repository handling currently active open trading positions."""

    def __init__(self):
        super().__init__(ActivePosition)

    def get_by_user(self, db: Session, user_id: str) -> List[ActivePosition]:
        """Fetches all active positions open for a target user."""
        return db.query(ActivePosition).filter(ActivePosition.user_id == user_id).all()

    def get_by_user_and_symbol(self, db: Session, user_id: str, symbol: str) -> List[ActivePosition]:
        """Fetches active positions matching both user and currency pair context."""
        return db.query(ActivePosition).filter(
            ActivePosition.user_id == user_id,
            ActivePosition.symbol == symbol
        ).all()


class WatchlistRepository(BaseRepository[Watchlist]):
    """Repository handling user-defined watchlists."""

    def __init__(self):
        super().__init__(Watchlist)

    def get_by_user(self, db: Session, user_id: str) -> List[Watchlist]:
        """Fetches watchlists associated with a target user."""
        return db.query(Watchlist).filter(Watchlist.user_id == user_id).all()


class WatchlistItemRepository(BaseRepository[WatchlistItem]):
    """Repository handling individual items nested inside watchlists."""

    def __init__(self):
        super().__init__(WatchlistItem)

    def get_by_watchlist(self, db: Session, watchlist_id: int) -> List[WatchlistItem]:
        """Fetches all active item tickers assigned to a single watchlist."""
        return db.query(WatchlistItem).filter(WatchlistItem.watchlist_id == watchlist_id).all()


class NotificationRepository(BaseRepository[Notification]):
    """Repository handling system-wide risk and operational notifications."""

    def __init__(self):
        super().__init__(Notification)

    def get_unread_by_user(self, db: Session, user_id: str) -> List[Notification]:
        """Fetches only unread system warning and operational notices."""
        return db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).order_by(Notification.created_at.desc()).all()

    def get_all_by_user(self, db: Session, user_id: str, limit: int = 50) -> List[Notification]:
        """Fetches historical notifications for a user up to a specified limit."""
        return db.query(Notification).filter(
            Notification.user_id == user_id
        ).order_by(Notification.created_at.desc()).limit(limit).all()


class AuditLogRepository(BaseRepository[AuditLog]):
    """Repository handling operational system audit logging."""

    def __init__(self):
        super().__init__(AuditLog)

    def get_by_user(self, db: Session, user_id: str, limit: int = 100) -> List[AuditLog]:
        """Fetches system event listings associated with a target user."""
        return db.query(AuditLog).filter(AuditLog.user_id == user_id).order_by(
            AuditLog.created_at.desc()
        ).limit(limit).all()

    def log_event(
        self,
        db: Session,
        user_id: Optional[str],
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[str] = None,
    ) -> AuditLog:
        """
        Generates and commits a structured operational audit log entry to the database.
        """
        log_entry = {
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "ip_address": ip_address,
            "details": details,
        }
        return self.create(db, obj_in=log_entry)


# Singleton Repository Instances for unified imports
user_repo = UserRepository()
settings_repo = UserSettingsRepository()
strategy_repo = SavedStrategyRepository()
backtest_repo = SavedBacktestRepository()
optimization_repo = SavedOptimizationRepository()
ai_analysis_repo = SavedAIAnalysisRepository()
report_repo = SavedReportRepository()

# v4.5 Singleton Repositories
position_repo = ActivePositionRepository()
watchlist_repo = WatchlistRepository()
watchlist_item_repo = WatchlistItemRepository()
notification_repo = NotificationRepository()

audit_repo = AuditLogRepository()
