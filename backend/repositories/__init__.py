# backend/repositories/__init__.py
"""
Quantoryx — Repositories Package Initialization.

This file exports singleton repository instances, exposing uniform data-access
APIs for services and routing layers.
"""

from backend.repositories.base import BaseRepository
from backend.repositories.repositories import (
    UserRepository,
    UserSettingsRepository,
    SavedStrategyRepository,
    SavedBacktestRepository,
    SavedOptimizationRepository,
    SavedAIAnalysisRepository,
    SavedReportRepository,
    ActivePositionRepository,
    WatchlistRepository,
    WatchlistItemRepository,
    NotificationRepository,
    AuditLogRepository,
    user_repo,
    settings_repo,
    strategy_repo,
    backtest_repo,
    optimization_repo,
    ai_analysis_repo,
    report_repo,
    position_repo,
    watchlist_repo,
    watchlist_item_repo,
    notification_repo,
    audit_repo,
)

__all__ = [
    "BaseRepository",
    "UserRepository",
    "UserSettingsRepository",
    "SavedStrategyRepository",
    "SavedBacktestRepository",
    "SavedOptimizationRepository",
    "SavedAIAnalysisRepository",
    "SavedReportRepository",
    "ActivePositionRepository",
    "WatchlistRepository",
    "WatchlistItemRepository",
    "NotificationRepository",
    "AuditLogRepository",
    "user_repo",
    "settings_repo",
    "strategy_repo",
    "backtest_repo",
    "optimization_repo",
    "ai_analysis_repo",
    "report_repo",
    "position_repo",
    "watchlist_repo",
    "watchlist_item_repo",
    "notification_repo",
    "audit_repo",
]
