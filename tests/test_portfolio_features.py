# tests/test_portfolio_features.py
"""
Integration tests verifying RDBMS configurations, user default preference updates,
watchlist operations, and risk notification pipelines.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.connection import Base
from backend.models.models import User, UserSettings, ActivePosition, Watchlist, WatchlistItem, Notification
from backend.services.user_service import UserService
from backend.services.portfolio_services import PortfolioService
from backend.schemas.api_schemas import UserSettingsUpdateRequest


@pytest.fixture
def db_session():
    """Initializes an isolated in-memory SQLite database for secure transactional audits."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    
    SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionClass()
    
    # Bootstrap a mock user and corresponding operational settings records
    user_data = {
        "id": "test-user-uuid-999",
        "username": "test_trader",
        "email": "test_trader@quantoryx.com",
        "hashed_password": "securebcryptpackagedhash",
        "role": "user",
        "is_active": True
    }
    db_user = User(**user_data)
    session.add(db_user)
    
    settings_data = {
        "user_id": "test-user-uuid-999",
        "default_symbol": "EURUSD",
        "default_timeframe": "1H",
        "risk_per_trade_pct": 1.0,
        "leverage": 30.0,
        "spread": 0.0002,
        "confidence_threshold": 65.0
    }
    db_settings = UserSettings(**settings_data)
    session.add(db_settings)
    
    session.commit()
    
    yield session
    session.close()


def test_update_user_settings_service(db_session):
    """Verifies modification and persistence of user parameter preferences."""
    user_id = "test-user-uuid-999"
    
    # 1. Fetch current settings
    settings = UserService.get_user_settings(user_id=user_id, db=db_session)
    assert settings is not None
    assert settings.default_symbol == "EURUSD"
    assert settings.leverage == 30.0

    # 2. Update settings via request schema payload
    update_request = UserSettingsUpdateRequest(
        default_symbol="GBPUSD",
        leverage=50.0,
        risk_per_trade_pct=2.0
    )
    
    updated = UserService.update_user_settings(
        user_id=user_id,
        update_request=update_request,
        db=db_session
    )
    
    assert updated is not None
    assert updated.default_symbol == "GBPUSD"
    assert updated.leverage == 50.0
    assert updated.risk_per_trade_pct == 2.0


def test_active_holdings_persistence(db_session):
    """Verifies database insertion and removal of open trade records."""
    user_id = "test-user-uuid-999"
    
    # 1. Confirm initial positions count is empty
    positions = PortfolioService.get_active_positions(user_id=user_id, db=db_session)
    assert len(positions) == 0

    # 2. Persist a newly opened position
    pos_obj = PortfolioService.persist_open_position(
        user_id=user_id,
        symbol="EURUSD",
        direction="LONG",
        entry_price=1.1200,
        size=10000.0,
        stop_loss=1.1100,
        take_profit=1.1400,
        required_margin=373.33,
        entry_regime="Trending Bullish",
        db=db_session
    )
    
    assert pos_obj is not None
    assert pos_obj.id is not None
    
    # 3. Verify retrieved list contains the position
    positions = PortfolioService.get_active_positions(user_id=user_id, db=db_session)
    assert len(positions) == 1
    assert positions[0].symbol == "EURUSD"
    assert positions[0].entry_regime == "Trending Bullish"

    # 4. Remove position upon transaction closure
    success = PortfolioService.remove_closed_position(
        user_id=user_id,
        position_id=pos_obj.id,
        db=db_session
    )
    
    assert success is True
    
    # 5. Confirm positions are empty again
    positions = PortfolioService.get_active_positions(user_id=user_id, db=db_session)
    assert len(positions) == 0


def test_watchlist_management(db_session):
    """Verifies watchlist grouping creations, item additions, and deletions."""
    user_id = "test-user-uuid-999"
    
    # 1. Create a named watchlist
    watchlist = PortfolioService.create_watchlist(user_id=user_id, name="Forex Majors", db=db_session)
    assert watchlist is not None
    assert watchlist.name == "Forex Majors"
    
    # 2. Append symbols into the watchlist
    item1 = PortfolioService.add_symbol_to_watchlist(user_id=user_id, watchlist_id=watchlist.id, symbol="GBPUSD", db=db_session)
    item2 = PortfolioService.add_symbol_to_watchlist(user_id=user_id, watchlist_id=watchlist.id, symbol="EURUSD", db=db_session)
    
    assert item1 is not None
    assert item2 is not None
    
    # 3. Assert watchlist query contains items
    watchlists = PortfolioService.get_watchlists_by_user(user_id=user_id, db=db_session)
    assert len(watchlists) == 1
    assert len(watchlists[0].items) == 2
    
    # 4. Remove an item
    removed = PortfolioService.remove_symbol_from_watchlist(
        user_id=user_id, 
        watchlist_id=watchlist.id, 
        item_id=item1.id, 
        db=db_session
    )
    assert removed is True
    
    # 5. Assert remaining items count
    watchlists = PortfolioService.get_watchlists_by_user(user_id=user_id, db=db_session)
    assert len(watchlists[0].items) == 1


def test_notification_alerts(db_session):
    """Verifies dispatch, unread filters, and read closures of notification notices."""
    user_id = "test-user-uuid-999"
    
    # 1. Dispatch two notification notices
    notice1 = PortfolioService.dispatch_notification(
        user_id=user_id,
        title="Leverage Warning",
        message="Risk exposure has crossed standard thresholds.",
        db=db_session
    )
    notice2 = PortfolioService.dispatch_notification(
        user_id=user_id,
        title="Margin Call Alert",
        message="Margin levels are critically low.",
        db=db_session
    )
    
    assert notice1 is not None
    assert notice2 is not None
    
    # 2. Get only unread alerts
    unread = PortfolioService.get_notifications_by_user(user_id=user_id, unread_only=True, db=db_session)
    assert len(unread) == 2
    
    # 3. Dismiss a single alert
    success = PortfolioService.mark_notification_read(user_id=user_id, notification_id=notice1.id, db=db_session)
    assert success is True
    
    # 4. Assert unread count has decreased
    unread = PortfolioService.get_notifications_by_user(user_id=user_id, unread_only=True, db=db_session)
    assert len(unread) == 1
    assert unread[0].title == "Margin Call Alert"
    
    # 5. Dismiss remaining alerts
    PortfolioService.dismiss_all_notifications(user_id=user_id, db=db_session)
    unread = PortfolioService.get_notifications_by_user(user_id=user_id, unread_only=True, db=db_session)
    assert len(unread) == 0
