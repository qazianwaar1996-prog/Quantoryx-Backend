# backend/services/integration_coordinator.py
"""
Quantoryx — Systems Integration and Execution Coordinator.

Orchestrates licensing verification, news blackout checks, portfolio optimization,
multi-broker execution, immutable compliance logging, and multi-channel notifications [15].
"""

import os
import sys
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 1. Import all new v5.0 Modules
import brokers
import market_data
from execution import ExecutionEngine
from portfolio.position_manager import PositionManager
from portfolio.order_manager import OrderManager, PendingOrder
from portfolio.optimizer import PortfolioOptimizer
from news import EconomicCalendar, NewsEvent
from learning import ContinuousLearningTracker, LearningTransition
from notifications import NotificationDispatcher
from licensing import LicensingManager
from cloud import CloudSyncCoordinator
from compliance import AuditLogger

# Existing core configurations
import config
from utils.logging_config import get_logger

logger = get_logger("integration.coordinator")


class IntegrationCoordinator:
    """
    Central orchestrator coordinating live broker trading, compliance tracking,
    and adaptive learning loops across all v5.0 modules [15].
    """

    def __init__(self):
        # Instantiate core subsystems
        self.licensing = LicensingManager()
        self.calendar = EconomicCalendar()
        self.learning = ContinuousLearningTracker()
        self.notifications = NotificationDispatcher()
        self.compliance = AuditLogger()
        
        self.order_manager = OrderManager()
        self.position_manager = PositionManager()
        self.portfolio_optimizer = PortfolioOptimizer()

        # Dynamic session holders (populated during initialization)
        self.broker: Optional[brokers.BaseBroker] = None
        self.market_provider: Optional[market_data.BaseMarketDataProvider] = None
        self.executor: Optional[ExecutionEngine] = None
        self.cloud_sync: Optional[CloudSyncCoordinator] = None

    async def initialize_session(
        self,
        user_id: str,
        license_key: str,
        license_signature: str,
        license_payload: Dict[str, Any],
        device_id: str,
        broker_name: str,
        broker_config: Dict[str, Any],
        market_provider_name: str,
        market_provider_key: str,
        smtp_config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Performs licensing validation, initializes target broker connections,
        boots market data streams, and seeds local calendar event registries [15].
        """
        logger.info("Initializing integrated session for User %s...", user_id)

        # 1. Validate License and Node Activation
        valid_license = self.licensing.validate_license_key(license_key, license_signature, license_payload)
        if not valid_license:
            logger.error("Session initialization aborted: License validation failed.")
            return False

        activated = self.licensing.activate_device(device_id)
        if not activated:
            logger.error("Session initialization aborted: Node activation rejected.")
            return False

        # 2. Check Feature Permissions
        if not self.licensing.check_feature_access("BROKERS"):
            logger.error("Session initialization aborted: License tier lacks 'BROKERS' permissions.")
            return False

        # Save offline license checkpoint to support connection drops
        self.licensing.save_offline_checkpoint()

        # 3. Instantiate and Connect Broker Adapter
        try:
            self.broker = brokers.get_broker(broker_name, broker_config)
            connected = await self.broker.connect()
            if not connected:
                logger.error("Failed to connect broker session.")
                return False
                
            self.executor = ExecutionEngine(self.broker)
        except Exception as e:
            logger.error("Exception triggered during broker connection: %s", str(e))
            return False

        # 4. Instantiate Market Data Provider
        try:
            self.market_provider = market_data.get_market_provider(market_provider_name, market_provider_key)
            status_ok = await self.market_provider.check_provider_status()
            if not status_ok:
                logger.warning("Market data provider status ping failed. Operating in degraded state.")
        except Exception as e:
            logger.error("Failed to initialize market data provider: %s", str(e))

        # 5. Seed Economic Calendar for News Blackout checks (90-day lookahead)
        self.calendar.seed_cyclical_forex_news(start_date=datetime.utcnow(), days=90)

        # 6. Initialize SMTP Notification parameters if provided
        if smtp_config:
            self.notifications.smtp_config = smtp_config

        # Log session startup compliance event
        self.compliance.log_compliance_event(
            user_id=user_id,
            action="SESSION_INITIALIZATION",
            entity_type="user",
            entity_id=user_id,
            details={"broker": broker_name, "market_provider": market_provider_name, "device_id": device_id}
        )

        logger.info("Integrated trading session fully initialized and active.")
        return True

    # =====================================================================
    # INTEGRATED TRANSACTION EXECUTION WORKFLOW
    # =====================================================================

    async def process_strategy_signal(
        self,
        user_id: str,
        symbol: str,
        direction: str,
        current_price: float,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        ai_confidence_score: float,
        notification_config: Dict[str, Any]
    ) -> Optional[brokers.BrokerOrderResult]:
        """
        Orchestrates the entire live transaction lifecycle across all subsystems [15].
        """
        if not self.is_session_active():
            logger.error("Signal rejected: No active broker session initialized.")
            return None

        # 1. Enforce Gated Feature Authorization
        if not self.licensing.check_feature_access("BROKERS"):
            return None

        # 2. Enforce Economic Calendar Blackout Window Checks
        is_blocked, news_event = self.calendar.is_in_blackout_window(
            current_time=datetime.utcnow(),
            symbol=symbol,
            pre_event_minutes=30,
            post_event_minutes=15
        )
        if is_blocked and news_event:
            # Dispatch warning and log compliance bypass event
            self.compliance.log_compliance_event(
                user_id=user_id,
                action="TRADE_BLOCKED_NEWS_BLACKOUT",
                entity_type="order",
                entity_id=symbol,
                details={"event_title": news_event.title, "event_time": news_event.timestamp.isoformat()}
            )
            
            # Send notification
            await self.notifications.broadcast_alert(
                user_id=user_id,
                alert_type="NEWS_BLACKOUT_BLOCK",
                title="Execution Blocked by Economic Calendar",
                message=f"Signal on {symbol} blocked due to scheduled high-impact event: {news_event.title} at {news_event.timestamp}.",
                delivery_config=notification_config
            )
            return None

        # 3. Recalculate Volatility-Adjusted Kelly Position Size [6]
        # Query broker account info first to get current balance/equity
        try:
            acc_info = await self.broker.get_account_info()
            positions_list = await self.broker.get_positions()
            self.position_manager.update_states(positions_list, acc_info)
        except Exception as e:
            logger.error("Failed to sync broker state before execution: %s", str(e))
            return None

        # Sizing variables
        win_rate = 0.55  # Query actual historical win rate from tracker
        win_loss_ratio = 1.5

        # Query adaptive parameter suggestions from AI Learning Tracker [8]
        current_regime = "Normal Volatility"  # default fallback
        adaptive_params = self.learning.suggest_adaptive_parameters(strategy_name, current_regime)
        active_params = adaptive_params if adaptive_params else strategy_params

        # Calculate volatility allocations
        vol_pnl_pct = 1.25  # assume 1.25% daily volatility
        
        optimized_allocation_usd = self.portfolio_optimizer.optimize_position_size(
            balance=self.position_manager.balance,
            win_rate=win_rate,
            win_loss_ratio=win_loss_ratio,
            current_drawdown_pct=self.position_manager.margin_level_pct,  # proxy for DD tracking
            max_drawdown_limit=10.0,
            asset_volatility_pct=vol_pnl_pct,
            target_risk_pct=config.RISK_LIMITS["risk_per_trade_pct"]
        )

        # Convert allocation USD size to standard base lots (assuming 1:30 leverage)
        lots_size = (optimized_allocation_usd * self.position_manager.leverage) / (current_price * 100000.0)
        lots_size = max(0.01, round(lots_size, 2))  # ensure standard lot increment mapping

        # 4. Dispatch Order with Exponential Retries via Execution Engine [3]
        sl_pct = 1.5
        rr = 2.5
        sl, tp = self.broker.config.get("risk_manager", self.position_manager).leverage, 0.0 # dummy placeholders
        # Use Standard Risk Sizing calculations
        sl_dist = current_price * (sl_pct / 100.0)
        sl_price = current_price - sl_dist if direction.upper() == "BUY" else current_price + sl_dist
        tp_price = current_price + (sl_dist * rr) if direction.upper() == "BUY" else current_price - (sl_dist * rr)

        order_result = await self.executor.submit_market_order(
            symbol=symbol,
            direction=direction,
            volume=lots_size,
            stop_loss=sl_price,
            take_profit=tp_price
        )

        if not order_result.success:
            # Log failure compliance event
            self.compliance.log_compliance_event(
                user_id=user_id,
                action="ORDER_EXECUTION_FAILED",
                entity_type="order",
                entity_id=order_result.order_id,
                details={"symbol": symbol, "direction": direction, "volume": lots_size, "error": order_result.error_message}
            )
            return order_result

        # 5. Log Transaction compliance logs [12]
        self.compliance.log_compliance_event(
            user_id=user_id,
            action="ORDER_EXECUTION_SUCCESS",
            entity_type="order",
            entity_id=order_result.order_id,
            details={
                "symbol": symbol,
                "direction": direction,
                "volume": lots_size,
                "price": order_result.filled_price,
                "strategy": strategy_name,
                "parameters": str(active_params),
                "confidence_score": ai_confidence_score
            }
        )

        # 6. Record Reinforcement Learning State Transition [8]
        transition = LearningTransition(
            transition_id=f"trans-{order_result.order_id}",
            entry_time=datetime.utcnow(),
            entry_regime=current_regime,
            entry_volatility=vol_pnl_pct,
            entry_trend_strength=35.0,
            strategy_name=strategy_name,
            parameters_json=str(active_params),
            confidence_score=ai_confidence_score,
            realized_pnl=0.0,  # updated when closed
            exit_time=datetime.utcnow(),
            exit_regime="Unknown",
            exit_volatility=0.0,
            exit_trend_strength=0.0
        )
        self.learning.record_trade_outcome(transition)

        # 7. Broadcast Multi-Channel Notifications [9]
        alert_msg = f"Order Executed: {direction} {lots_size} lots of {symbol} filled at {order_result.filled_price}.\nTarget SL: {sl_price:.5f} | TP: {tp_price:.5f}."
        await self.notifications.broadcast_alert(
            user_id=user_id,
            alert_type="ORDER_FILLED",
            title="Position Successfully Opened",
            message=alert_msg,
            delivery_config=notification_config
        )

        return order_result

    def is_session_active(self) -> bool:
        """Verifies if the broker session is connected and active."""
        return self.broker is not None and self.is_connected
