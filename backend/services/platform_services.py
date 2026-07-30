# backend/services/platform_services.py
"""
Quantoryx — Platform Feature Services (v6.0).

Implements the persistence and business logic backing the alerting engine,
trade journal, live signal feed, subscription billing, and the visual strategy
builder. Mirrors the transactional patterns used by PortfolioService so the
router layer stays a thin validation boundary.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

import config
from backend.models import (
    Alert,
    BuilderStrategy,
    Invoice,
    JournalEntry,
    Subscription,
    TradingSignal,
)
from utils.logging_config import get_logger

logger = get_logger("backend.services.platform_services")

# Timeframe used for the market-watch feed; first supported entry keeps this
# aligned with whatever the deployment actually has data for.
_TICKER_TIMEFRAME = "1H" if "1H" in config.SUPPORTED_TIMEFRAMES else config.SUPPORTED_TIMEFRAMES[0]


# =====================================================================
# STATIC CATALOGUES
# =====================================================================
# Plan definitions are product configuration rather than user data, so they
# live in code and are served read-only. Move to a table if pricing becomes
# dynamic or region-specific.

SUBSCRIPTION_PLANS: List[Dict[str, Any]] = [
    {
        "id": "starter",
        "name": "Starter",
        "desc": "Explore the platform and validate your first ideas.",
        "price": {"mo": 0.0, "yr": 0.0},
        "feats": [
            ["3 strategies", 1], ["100 backtests / mo", 1], ["Basic AI insights", 1],
            ["Email alerts", 1], ["Optimization engine", 0], ["Live signals", 0],
            ["API access", 0], ["Priority support", 0],
        ],
    },
    {
        "id": "pro",
        "name": "Pro",
        "desc": "For active traders running multiple live strategies.",
        "popular": True,
        "price": {"mo": 49.0, "yr": 470.0},
        "feats": [
            ["Unlimited strategies", 1], ["Unlimited backtests", 1], ["Full AI assistant", 1],
            ["Email + push + SMS alerts", 1], ["Grid & genetic optimization", 1],
            ["Live signals", 1], ["API access", 0], ["Priority support", 0],
        ],
    },
    {
        "id": "quant",
        "name": "Quant",
        "desc": "Institutional tooling, automation, and dedicated support.",
        "price": {"mo": 149.0, "yr": 1430.0},
        "feats": [
            ["Everything in Pro", 1], ["Walk-forward analysis", 1], ["Custom AI model tuning", 1],
            ["Webhook + broker routing", 1], ["Multi-account portfolios", 1],
            ["White-label reports", 1], ["Full REST + WS API", 1], ["Priority support", 1],
        ],
    },
]

PLAN_QUOTAS: Dict[str, Dict[str, Any]] = {
    "starter": {"backtests": 100, "ai": 200, "optimizations": 5, "strategies": 3},
    "pro":     {"backtests": 1000, "ai": 2000, "optimizations": 50, "strategies": "∞"},
    "quant":   {"backtests": "∞", "ai": "∞", "optimizations": "∞", "strategies": "∞"},
}

BUILDER_BLOCKS: List[Dict[str, Any]] = [
    {"cat": "Indicators", "items": [
        {"id": "ema", "icon": "📈", "name": "EMA", "params": "fast_period: 10, slow_period: 30"},
        {"id": "rsi", "icon": "📊", "name": "RSI", "params": "period: 14, oversold: 30, overbought: 70"},
        {"id": "macd", "icon": "〰", "name": "MACD", "params": "12, 26, 9"},
        {"id": "bollinger", "icon": "🎚", "name": "Bollinger Bands", "params": "period: 20, std_dev: 2.0"},
        {"id": "atr", "icon": "📏", "name": "ATR", "params": "period: 14"},
    ]},
    {"cat": "Conditions", "items": [
        {"id": "cross_up", "icon": "⬆", "name": "Crosses Above", "params": "a > b"},
        {"id": "cross_dn", "icon": "⬇", "name": "Crosses Below", "params": "a < b"},
        {"id": "thresh", "icon": "⚖", "name": "Threshold", "params": "value vs n"},
    ]},
    {"cat": "Risk", "items": [
        {"id": "sl", "icon": "🛑", "name": "Stop Loss", "params": "3.0%"},
        {"id": "tp", "icon": "🎯", "name": "Take Profit", "params": "6.0%"},
        {"id": "size", "icon": "💰", "name": "Position Size", "params": "1% risk"},
        {"id": "trail", "icon": "🔄", "name": "Trailing Stop", "params": "1.5 ATR"},
    ]},
    {"cat": "Actions", "items": [
        {"id": "buy", "icon": "🟢", "name": "Enter Long", "params": "market"},
        {"id": "sell", "icon": "🔴", "name": "Enter Short", "params": "market"},
        {"id": "exit", "icon": "⏹", "name": "Close Position", "params": "all"},
    ]},
]

HELP_FAQ: List[Dict[str, str]] = [
    {"q": "How accurate are the backtest results?",
     "a": "Backtests run against the historical dataset loaded in the backend engine using the spread "
          "and leverage configured in Settings. Results are indicative, not guarantees — validate with "
          "walk-forward analysis before committing capital."},
    {"q": "What powers the AI assistant?",
     "a": "POST /api/ai-analysis runs the decision engine: market-regime detection, strategy selection, "
          "a confidence model, and a natural-language explanation engine."},
    {"q": "Why did an optimization run fail to queue?",
     "a": "Optimization and walk-forward are dispatched to Celery workers and require Redis. Start Redis "
          "and a worker, or run the equivalent CLI scripts shipped in the repository."},
    {"q": "Can I connect my own broker?",
     "a": "Broker adapters for MT5, OANDA, Interactive Brokers, cTrader, DXtrade and Pepperstone ship with "
          "the platform. Configure credentials, then map a strategy to an execution account."},
    {"q": "Is my data secure?",
     "a": "Authentication uses signed JWT access and refresh tokens. Access tokens rotate automatically on "
          "expiry and signing out revokes the refresh token server-side."},
    {"q": "Can I export my trade history?",
     "a": "Yes. The Trade Journal exports a full trade-by-trade CSV, and generated reports are listed under "
          "Reports for download."},
]

HELP_DOCS: List[Dict[str, str]] = [
    {"icon": "🚀", "title": "Getting Started", "desc": "Register, sign in, and run your first backtest against the live engine.", "time": "5 min read"},
    {"icon": "📋", "title": "Building Strategies", "desc": "Compose indicators, conditions, and risk rules in the visual builder.", "time": "12 min read"},
    {"icon": "▶", "title": "Backtesting Guide", "desc": "Configure a run and interpret every KPI the engine returns.", "time": "9 min read"},
    {"icon": "⚙", "title": "Optimization Deep Dive", "desc": "Grid versus genetic search, and reading the parameter surface.", "time": "15 min read"},
    {"icon": "🤖", "title": "AI Assistant", "desc": "How the decision engine selects a strategy and scores confidence.", "time": "7 min read"},
    {"icon": "🔑", "title": "API Reference", "desc": "Every REST route and the WebSocket channel exposed by the backend.", "time": "20 min read"},
]


class AlertService:
    """Create, arm, and evaluate user-defined market alerts."""

    @classmethod
    def list_alerts(cls, user_id: str, db: Session) -> List[Alert]:
        return (
            db.query(Alert)
            .filter(Alert.user_id == user_id)
            .order_by(Alert.created_at.desc())
            .all()
        )

    @classmethod
    def create_alert(cls, user_id: str, payload: Dict[str, Any], db: Session) -> Alert:
        condition = payload.get("cond") or " ".join(
            str(p) for p in (payload.get("instrument"), payload.get("op"), payload.get("value")) if p
        )
        alert = Alert(
            user_id=user_id,
            name=payload["name"],
            alert_type=payload.get("type", "price"),
            condition=condition or "—",
            instrument=payload.get("instrument"),
            operator=payload.get("op"),
            threshold=str(payload.get("value")) if payload.get("value") is not None else None,
            strategy=payload.get("strategy"),
            channels=payload.get("channel") or [],
            is_active=bool(payload.get("on", True)),
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        logger.info("Alert created for user %s: %s", user_id, alert.name)
        return alert

    @classmethod
    def set_active(cls, user_id: str, alert_id: int, is_active: bool, db: Session) -> Optional[Alert]:
        alert = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == user_id).first()
        if not alert:
            return None
        alert.is_active = is_active
        db.commit()
        db.refresh(alert)
        return alert

    @classmethod
    def delete_alert(cls, user_id: str, alert_id: int, db: Session) -> bool:
        alert = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == user_id).first()
        if not alert:
            return False
        db.delete(alert)
        db.commit()
        return True

    @classmethod
    def seed_defaults(cls, user_id: str, db: Session) -> None:
        """Provision a starter alert set so a new account is not empty."""
        if db.query(Alert).filter(Alert.user_id == user_id).count():
            return
        defaults = [
            {"name": "Portfolio drawdown guard", "type": "risk",
             "cond": "Drawdown < -12%", "strategy": "All strategies", "channel": ["email"]},
            {"name": f"{config.SUPPORTED_PAIRS[0]} breakout", "type": "price",
             "cond": f"{config.SUPPORTED_PAIRS[0]} > 1.0900", "strategy": "Breakout", "channel": ["push"]},
        ]
        for d in defaults:
            cls.create_alert(user_id, d, db)


class JournalService:
    """Persist trader reflections attached to executed trades."""

    @classmethod
    def list_entries(cls, user_id: str, db: Session) -> List[JournalEntry]:
        return (
            db.query(JournalEntry)
            .filter(JournalEntry.user_id == user_id)
            .order_by(JournalEntry.traded_at.desc())
            .all()
        )

    @classmethod
    def create_entry(cls, user_id: str, payload: Dict[str, Any], db: Session) -> JournalEntry:
        entry = JournalEntry(
            user_id=user_id,
            symbol=payload["pair"],
            direction=payload.get("dir", "Long"),
            pnl=float(payload.get("pnl", 0.0)),
            rating=int(payload.get("rating", 3)),
            tags=payload.get("tags") or [],
            note=payload.get("note", ""),
            strategy=payload.get("strategy"),
            traded_at=datetime.utcnow(),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    @classmethod
    def delete_entry(cls, user_id: str, entry_id: int, db: Session) -> bool:
        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.id == entry_id, JournalEntry.user_id == user_id)
            .first()
        )
        if not entry:
            return False
        db.delete(entry)
        db.commit()
        return True


class SignalService:
    """Expose entry signals and market-watch pricing."""

    @classmethod
    def list_signals(cls, user_id: str, db: Session) -> List[TradingSignal]:
        return (
            db.query(TradingSignal)
            .filter(TradingSignal.user_id == user_id)
            .order_by(TradingSignal.created_at.desc())
            .limit(50)
            .all()
        )

    @classmethod
    def record_signal(cls, user_id: str, payload: Dict[str, Any], db: Session) -> TradingSignal:
        signal = TradingSignal(
            user_id=user_id,
            symbol=payload.get("symbol", "EURUSD"),
            direction=payload.get("direction", "buy"),
            entry_price=payload.get("entry_price"),
            stop_loss=payload.get("stop_loss"),
            take_profit=payload.get("take_profit"),
            confidence=float(payload.get("confidence", 0.0)),
            risk_reward=payload.get("risk_reward"),
            strategy=payload.get("strategy"),
            timeframe=payload.get("timeframe"),
            signal_status=payload.get("status", "active"),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal

    @classmethod
    def market_tickers(cls) -> List[Dict[str, Any]]:
        """
        Latest close and session change for every supported pair, sourced from
        the cached OHLC dataset the engine already loads. Falls back to a flat
        quote when a pair has no local history yet.
        """
        from backend.services.quantoryx_service import QuantoryxService  # local import avoids a cycle

        out: List[Dict[str, Any]] = []
        for pair in config.SUPPORTED_PAIRS:
            price, change = 0.0, 0.0
            try:
                df = QuantoryxService._load_data_safely(pair, _TICKER_TIMEFRAME)  # noqa: SLF001
                if df is not None and not df.empty and "close" in df:
                    closes = df["close"].dropna()
                    if len(closes) >= 2:
                        price = float(closes.iloc[-1])
                        prev = float(closes.iloc[-2])
                        change = ((price - prev) / prev * 100.0) if prev else 0.0
                    elif len(closes) == 1:
                        price = float(closes.iloc[-1])
            except Exception as exc:  # data gaps must never break the feed
                logger.debug("Ticker unavailable for %s: %s", pair, exc)
            out.append({"pair": pair, "px": round(price, 5), "chg": round(change, 3)})
        return out


class BillingService:
    """Subscription tiers, invoices, and quota consumption."""

    @classmethod
    def get_or_create_subscription(cls, user_id: str, db: Session) -> Subscription:
        sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
        if not sub:
            sub = Subscription(
                user_id=user_id,
                plan_id="starter",
                billing_cycle="mo",
                plan_status="active",
                renews_at=datetime.utcnow() + timedelta(days=30),
            )
            db.add(sub)
            db.commit()
            db.refresh(sub)
        return sub

    @classmethod
    def subscribe(cls, user_id: str, plan_id: str, cycle: str, db: Session) -> Subscription:
        sub = cls.get_or_create_subscription(user_id, db)
        sub.plan_id = plan_id
        sub.billing_cycle = cycle or "mo"
        sub.renews_at = datetime.utcnow() + timedelta(days=365 if cycle == "yr" else 30)
        db.commit()
        db.refresh(sub)

        plan = next((p for p in SUBSCRIPTION_PLANS if p["id"] == plan_id), None)
        amount = float(plan["price"].get(sub.billing_cycle, 0.0)) if plan else 0.0
        if amount > 0:
            now = datetime.utcnow()
            db.add(Invoice(
                user_id=user_id,
                reference=f"INV-{now:%Y-%m}-{sub.id:04d}",
                plan_label=f"{plan['name']} {'Yearly' if sub.billing_cycle == 'yr' else 'Monthly'}",
                amount=amount,
                invoice_status="paid",
            ))
            db.commit()
        logger.info("User %s switched to plan %s (%s)", user_id, plan_id, sub.billing_cycle)
        return sub

    @classmethod
    def list_invoices(cls, user_id: str, db: Session) -> List[Invoice]:
        return (
            db.query(Invoice)
            .filter(Invoice.user_id == user_id)
            .order_by(Invoice.issued_at.desc())
            .all()
        )

    @classmethod
    def usage(cls, user_id: str, db: Session) -> List[Dict[str, Any]]:
        """Quota consumption for the active cycle, counted from persisted runs."""
        from backend.models import SavedAIAnalysis, SavedBacktest, SavedOptimization, SavedStrategy

        sub = cls.get_or_create_subscription(user_id, db)
        quota = PLAN_QUOTAS.get(sub.plan_id, PLAN_QUOTAS["starter"])
        cycle_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        def _count(model) -> int:
            try:
                return (
                    db.query(model)
                    .filter(model.user_id == user_id, model.created_at >= cycle_start)
                    .count()
                )
            except Exception:
                return 0

        return [
            {"label": "Backtests this month", "used": _count(SavedBacktest), "limit": quota["backtests"]},
            {"label": "AI analyses", "used": _count(SavedAIAnalysis), "limit": quota["ai"]},
            {"label": "Optimization runs", "used": _count(SavedOptimization), "limit": quota["optimizations"]},
            {"label": "Saved strategies",
             "used": db.query(SavedStrategy).filter(SavedStrategy.user_id == user_id).count(),
             "limit": quota["strategies"]},
        ]


class BuilderService:
    """Persist visual strategy-builder compositions."""

    @classmethod
    def blocks(cls) -> List[Dict[str, Any]]:
        return BUILDER_BLOCKS

    @classmethod
    def save(cls, user_id: str, payload: Dict[str, Any], db: Session) -> BuilderStrategy:
        strategy = BuilderStrategy(
            user_id=user_id,
            name=payload.get("name", "Untitled Strategy"),
            symbol=payload.get("symbol", "EURUSD"),
            timeframe=payload.get("timeframe", "1H"),
            nodes=payload.get("nodes") or [],
        )
        db.add(strategy)
        db.commit()
        db.refresh(strategy)
        logger.info("Builder strategy '%s' saved for user %s", strategy.name, user_id)
        return strategy

    @classmethod
    def list_saved(cls, user_id: str, db: Session) -> List[BuilderStrategy]:
        return (
            db.query(BuilderStrategy)
            .filter(BuilderStrategy.user_id == user_id)
            .order_by(BuilderStrategy.updated_at.desc())
            .all()
        )
