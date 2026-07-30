# backend/models/models.py
"""
Quantoryx — Relational Database Models.

This module maps out all database schema tables utilizing the SQLAlchemy ORM.
It defines relationships, strict constraint indexes, JSON data column mappings,
and operational audit logging structures portable across SQLite and PostgreSQL.
"""

from datetime import datetime
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.database.connection import Base


# =====================================================================
# USER IDENTITY & METADATA SCHEMAS
# =====================================================================

class User(Base):
    """Stores credentials, security role contexts, and profile states."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(String(20), nullable=False, default="user")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relational bindings
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    strategies = relationship("SavedStrategy", back_populates="user", cascade="all, delete-orphan")
    backtests = relationship("SavedBacktest", back_populates="user", cascade="all, delete-orphan")
    optimizations = relationship("SavedOptimization", back_populates="user", cascade="all, delete-orphan")
    ai_analyses = relationship("SavedAIAnalysis", back_populates="user", cascade="all, delete-orphan")
    reports = relationship("SavedReport", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    
    # v4.5 Relational Bindings
    active_positions = relationship("ActivePosition", back_populates="user", cascade="all, delete-orphan")
    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    # v6.0 Relational Bindings
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
    journal_entries = relationship("JournalEntry", back_populates="user", cascade="all, delete-orphan")
    signals = relationship("TradingSignal", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="user", cascade="all, delete-orphan")
    builder_strategies = relationship("BuilderStrategy", back_populates="user", cascade="all, delete-orphan")


class UserSettings(Base):
    """Stores customized default operational configurations per user profile."""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    default_symbol = Column(String(20), nullable=False, default="EURUSD")
    default_timeframe = Column(String(10), nullable=False, default="1H")
    risk_per_trade_pct = Column(Float, nullable=False, default=1.0)
    leverage = Column(Float, nullable=False, default=30.0)
    spread = Column(Float, nullable=False, default=0.0002)
    confidence_threshold = Column(Float, nullable=False, default=65.0)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="settings")


# =====================================================================
# SAVED QUANTITATIVE ARTIFACT SCHEMAS
# =====================================================================

class SavedStrategy(Base):
    """Stores saved strategy parameter configurations."""
    __tablename__ = "saved_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(50), nullable=False)
    config_key = Column(String(50), nullable=False)
    parameters = Column(JSON, nullable=False)
    is_favorite = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="strategies")


class SavedBacktest(Base):
    """Stores completed backtest simulation metrics and parameters."""
    __tablename__ = "saved_backtests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    strategy_name = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    parameters = Column(JSON, nullable=False)
    net_profit = Column(Float, nullable=False)
    profit_factor = Column(Float, nullable=False)
    max_drawdown = Column(Float, nullable=False)
    win_rate = Column(Float, nullable=False)
    sharpe_ratio = Column(Float, nullable=False)
    trade_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="backtests")


class SavedOptimization(Base):
    """Stores parameter sweeps, combinations tested, and ranking metadata."""
    __tablename__ = "saved_optimizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    strategy_name = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    ranking_metric = Column(String(50), nullable=False)
    best_parameters = Column(JSON, nullable=False)
    total_combinations_tested = Column(Integer, nullable=False)
    top_results = Column(JSON, nullable=False)  # Stores top 10 ranked runs summary JSON
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="optimizations")


class SavedAIAnalysis(Base):
    """Stores cognitive AI strategy selection trace history parameters."""
    __tablename__ = "saved_ai_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    market_regime = Column(String(50), nullable=False)
    selected_strategy = Column(String(50), nullable=False)
    confidence_score = Column(Float, nullable=False)
    decision_action = Column(String(20), nullable=False)
    explanation = Column(Text, nullable=False)
    parameters = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="ai_analyses")


class SavedReport(Base):
    """Stores metadata of CSV outputs and ledger files compiled on disk."""
    __tablename__ = "saved_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    size_kb = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="reports")


# =====================================================================
# v4.5 PORTFOLIO ACTIVE STATE, WATCHLIST, & NOTIFICATION SCHEMAS
# =====================================================================

class ActivePosition(Base):
    """Stores currently open trading positions (Real-time Holdings State)."""
    __tablename__ = "active_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)  # LONG or SHORT
    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    entry_price = Column(Float, nullable=False)
    size = Column(Float, nullable=False)  # Quantity of units
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    required_margin = Column(Float, nullable=False)
    entry_regime = Column(String(50), nullable=True)

    # Relational bindings
    user = relationship("User", back_populates="active_positions")


class Watchlist(Base):
    """User watchlists grouping target symbols."""
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(50), nullable=False, default="Default")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="watchlists")
    items = relationship("WatchlistItem", back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(Base):
    """Individual symbols added inside a Watchlist."""
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    watchlist_id = Column(Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    watchlist = relationship("Watchlist", back_populates="items")


class Notification(Base):
    """User-targeted operational and risk warnings."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="notifications")


# =====================================================================
# SYSTEM AUDIT LOGGING SCHEMA
# =====================================================================

class AuditLog(Base):
    """Tracks critical system events, access controls, and operational tracing."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False)  # e.g., "USER_LOGIN", "BACKTEST_RUN"
    entity_type = Column(String(50), nullable=True)  # e.g., "backtest", "strategy"
    entity_id = Column(String(50), nullable=True)
    ip_address = Column(String(45), nullable=True)
    details = Column(Text, nullable=True)  # Store serialized event parameters
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="audit_logs")


# =====================================================================
# v6.0 SCHEMAS — ALERTS, JOURNAL, SIGNALS, BILLING & BUILDER
# =====================================================================

class Alert(Base):
    """User-defined market condition triggers evaluated against live data."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    alert_type = Column(String(20), nullable=False, default="price")  # price|risk|volatility|indicator|pnl
    condition = Column(String(120), nullable=False)                   # e.g. "EURUSD > 1.0900"
    instrument = Column(String(30), nullable=True)
    operator = Column(String(5), nullable=True)
    threshold = Column(String(30), nullable=True)
    strategy = Column(String(60), nullable=True)
    channels = Column(JSON, nullable=False, default=list)             # ["push","email","sms"]
    is_active = Column(Boolean, nullable=False, default=True)
    fired_count = Column(Integer, nullable=False, default=0)
    last_fired_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="alerts")


class JournalEntry(Base):
    """Trader-authored reflections attached to executed trades."""
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(30), nullable=False)
    direction = Column(String(10), nullable=False, default="Long")
    pnl = Column(Float, nullable=False, default=0.0)
    rating = Column(Integer, nullable=False, default=3)               # execution grade 1-5
    tags = Column(JSON, nullable=False, default=list)
    note = Column(Text, nullable=False, default="")
    strategy = Column(String(60), nullable=True)
    traded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="journal_entries")


class TradingSignal(Base):
    """Entry signals emitted by the decision engine for a user."""
    __tablename__ = "trading_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(30), nullable=False)
    direction = Column(String(10), nullable=False, default="buy")     # buy|sell
    entry_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    risk_reward = Column(String(20), nullable=True)
    strategy = Column(String(60), nullable=True)
    timeframe = Column(String(10), nullable=True)
    signal_status = Column(String(20), nullable=False, default="active")  # active|filled|closed
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="signals")


class Subscription(Base):
    """Billing plan currently attached to a user account."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(String(30), nullable=False, default="starter")   # starter|pro|quant
    billing_cycle = Column(String(10), nullable=False, default="mo")  # mo|yr
    plan_status = Column(String(20), nullable=False, default="active")
    renews_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="subscription")


class Invoice(Base):
    """Issued billing statements for a subscription."""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reference = Column(String(40), nullable=False)
    plan_label = Column(String(60), nullable=False)
    amount = Column(Float, nullable=False, default=0.0)
    invoice_status = Column(String(20), nullable=False, default="paid")
    issued_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="invoices")


class BuilderStrategy(Base):
    """Visual strategy-builder compositions (ordered block graph)."""
    __tablename__ = "builder_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(80), nullable=False, default="Untitled Strategy")
    symbol = Column(String(30), nullable=False, default="EURUSD")
    timeframe = Column(String(10), nullable=False, default="1H")
    nodes = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relational bindings
    user = relationship("User", back_populates="builder_strategies")
