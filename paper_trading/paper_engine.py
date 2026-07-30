# paper_trading/paper_engine.py
"""
paper_trading/paper_engine.py

Simulates a live-trading desk execution environment.
Supports leverage, spread, margin requirements, liquidation thresholds,
and records account financial metrics step-by-step.
Optionally integrates with RDBMS to persist active positions and notify users.
"""

import os
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.orm import Session

from risk.risk_manager import RiskManager
from market_regime.detector import MarketRegimeDetector
from backend.services.portfolio_services import PortfolioService


class PaperTradingEngine:
    """
    Simulates a live-trading desk execution environment.
    Supports leverage, spread, margin requirements, liquidation thresholds,
    and records account financial metrics step-by-step.
    """
    def __init__(
        self,
        starting_balance: float = 100000.0,
        leverage: float = 30.0,          # 1:30 leverage default
        spread_pct: float = 0.0002,       # 0.02% typical average spread (2 pips equivalent)
        risk_manager: RiskManager = None,
        margin_call_level: float = 100.0, # Margin call at 100% margin level
        stop_out_level: float = 50.0,     # Auto-liquidation at 50% margin level
        user_id: Optional[str] = None     # Optional user ID for database tracking
    ):
        self.balance = starting_balance
        self.equity = starting_balance
        self.leverage = leverage
        self.spread_pct = spread_pct
        self.margin_call_level = margin_call_level
        self.stop_out_level = stop_out_level
        self.user_id = user_id
        
        # Integration parameters
        self.risk_manager = risk_manager if risk_manager is not None else RiskManager()
        
        # State tracking
        self.active_positions: List[Dict[str, Any]] = []
        self.trade_logs: List[Dict[str, Any]] = []
        self.account_history: List[Dict[str, Any]] = []
        
        # Financial trackers
        self.used_margin = 0.0
        self.free_margin = starting_balance
        self.margin_level = float('inf')  # Equity / Used Margin * 100
        self.daily_pnl_tracker = 0.0
        
        # Alerts state
        self.has_sent_margin_warning = False

    def process_bar(self, timestamp: Any, row: pd.Series, regime: str, db: Optional[Session] = None):
        """
        Processes a single historical bar (tick simulation) to update unrealized P/L,
        evaluate stop/target hits, and check margin limits.
        """
        close_price = float(row['close'])
        high_price = float(row['high'])
        low_price = float(row['low'])
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(timestamp, 'strftime') else str(timestamp)

        # 1. Update Open Positions & Check Stop Loss / Take Profit
        still_active = []
        for pos in self.active_positions:
            is_closed = False
            exit_price = close_price
            reason = "Signal Exit"
            
            # Simulated bid/ask boundaries for order fills using spread
            pos_spread_cost = pos["entry_price"] * (self.spread_pct / 2.0)
            
            # Check Stop Loss
            if pos["direction"] == "LONG" and low_price <= pos["stop_loss"]:
                is_closed = True
                exit_price = pos["stop_loss"] - pos_spread_cost
                reason = "Stop Loss"
            elif pos["direction"] == "SHORT" and high_price >= pos["stop_loss"]:
                is_closed = True
                exit_price = pos["stop_loss"] + pos_spread_cost
                reason = "Stop Loss"
                
            # Check Take Profit
            elif pos["direction"] == "LONG" and high_price >= pos["take_profit"]:
                is_closed = True
                exit_price = pos["take_profit"] - pos_spread_cost
                reason = "Take Profit"
            elif pos["direction"] == "SHORT" and low_price <= pos["take_profit"]:
                is_closed = True
                exit_price = pos["take_profit"] + pos_spread_cost
                reason = "Take Profit"

            if is_closed:
                self._execute_close(pos, exit_price, reason, time_str, db=db)
            else:
                still_active.append(pos)
                
        self.active_positions = still_active

        # 2. Recalculate Equity, Margin & Check Liquidation
        self._recalculate_margins(close_price, db=db)
        
        if self.margin_level <= self.stop_out_level:
            self._liquidate_all_positions(close_price, time_str, "Stop Out / Liquidation", db=db)
            
        # 3. Log step snapshot
        self.account_history.append({
            "timestamp": time_str,
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "used_margin": round(self.used_margin, 2),
            "free_margin": round(self.free_margin, 2),
            "margin_level": round(self.margin_level, 2) if self.margin_level != float('inf') else 999.0,
            "active_trades": len(self.active_positions),
            "market_regime": regime
        })

    def execute_order(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        stop_loss_pct: float,
        rr_ratio: float,
        timestamp: Any,
        regime: str,
        db: Optional[Session] = None
    ) -> bool:
        """
        Places a virtual Buy/Sell order after checking margin and risk approvals.
        Includes spread costs in entry execution.
        """
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(timestamp, 'strftime') else str(timestamp)
        direction = direction.upper()
        
        # Calculate execution price incorporating spread
        spread_adjustment = current_price * (self.spread_pct / 2.0)
        execution_price = current_price + spread_adjustment if direction == "LONG" else current_price - spread_adjustment

        # Calculate SL/TP targets
        sl, tp = self.risk_manager.calculate_sl_tp(direction, execution_price, stop_loss_pct, rr_ratio)
        
        # Position Sizing
        quantity = self.risk_manager.calculate_position_size(self.balance, execution_price, sl)
        if quantity <= 0.0:
            return False

        notional_value = execution_price * quantity
        required_margin = notional_value / self.leverage
        
        if required_margin > self.free_margin:
            # Insufficient Margin check
            return False

        # Run Phase 5 Risk Management Gateways.
        # Exposure is measured as committed *margin* (capital actually at work)
        # rather than gross notional. On a leveraged account notional routinely
        # exceeds balance, so a notional-vs-balance cap would reject every
        # order; margin-based exposure is the correct, tradable interpretation.
        approved, reason = self.risk_manager.evaluate_entry_allowance(
            symbol=symbol,
            balance=self.balance,
            current_drawdown_pct=self.risk_manager.account_drawdown_pct,
            daily_loss_amount=self.daily_pnl_tracker,
            proposed_notional_size=required_margin
        )
        
        if not approved:
            return False

        # Execute Virtual Placement
        position = {
            "symbol": symbol,
            "direction": direction,
            "entry_time": time_str,
            "entry_price": execution_price,
            "size": quantity,
            "stop_loss": sl,
            "take_profit": tp,
            "required_margin": required_margin,
            "entry_regime": regime
        }
        
        # Optionally persist the active position in the database (v4.5)
        if db is not None and self.user_id is not None:
            db_pos = PortfolioService.persist_open_position(
                user_id=self.user_id,
                symbol=symbol,
                direction=direction,
                entry_price=execution_price,
                size=quantity,
                stop_loss=sl,
                take_profit=tp,
                required_margin=required_margin,
                entry_regime=regime,
                db=db
            )
            if db_pos:
                position["db_id"] = db_pos.id

        self.active_positions.append(position)
        # Track allocation in the same (margin) unit used by the exposure gate.
        self.risk_manager.register_trade_open(symbol, required_margin)
        self._recalculate_margins(current_price, db=db)
        
        return True

    def _execute_close(
        self, 
        position: Dict[str, Any], 
        exit_price: float, 
        reason: str, 
        timestamp_str: str, 
        db: Optional[Session] = None
    ):
        """
        Internal trade finalization, updating ledger balance and resetting risk exposures.
        """
        direction_mult = 1 if position["direction"] == "LONG" else -1
        pnl = (exit_price - position["entry_price"]) * position["size"] * direction_mult
        
        # Update balance
        self.balance += pnl
        if pnl < 0:
            self.daily_pnl_tracker += abs(pnl)

        trade_record = {
            "symbol": position["symbol"],
            "direction": position["direction"],
            "entry_time": position["entry_time"],
            "exit_time": timestamp_str,
            "entry_price": round(position["entry_price"], 5),
            "exit_price": round(exit_price, 5),
            "size": round(position["size"], 4),
            "pnl": round(pnl, 2),
            "reason": reason,
            "entry_regime": position["entry_regime"]
        }
        
        self.trade_logs.append(trade_record)

        # Optionally remove the position from active holdings in database (v4.5)
        if db is not None and self.user_id is not None and "db_id" in position:
            PortfolioService.remove_closed_position(
                user_id=self.user_id,
                position_id=position["db_id"],
                db=db
            )

        # Notify risk manager of close, releasing the same margin allocation
        # that was registered on open.
        self.risk_manager.register_trade_close(
            position["symbol"], position.get("required_margin", 0.0), pnl
        )

    def _recalculate_margins(self, current_price: float, db: Optional[Session] = None):
        """
        Recalculates floating Equity, Margin usage, Free Margin, and Margin levels.
        """
        unrealized_pnl = 0.0
        used_margin = 0.0
        
        for pos in self.active_positions:
            direction_mult = 1 if pos["direction"] == "LONG" else -1
            unrealized_pnl += (current_price - pos["entry_price"]) * pos["size"] * direction_mult
            used_margin += pos["required_margin"]
            
        self.equity = self.balance + unrealized_pnl
        self.used_margin = used_margin
        self.free_margin = max(0.0, self.equity - self.used_margin)
        
        if self.used_margin > 0:
            self.margin_level = (self.equity / self.used_margin) * 100.0
        else:
            self.margin_level = float('inf')

        # Trigger Margin Call alerts (v4.5)
        if self.margin_level <= self.margin_call_level:
            if not self.has_sent_margin_warning:
                if db is not None and self.user_id is not None:
                    PortfolioService.dispatch_notification(
                        user_id=self.user_id,
                        title="Margin Call Alert",
                        message=f"Critical: Margin level fell to {self.margin_level:.1f}%. Risk liquidation is imminent.",
                        db=db
                    )
                self.has_sent_margin_warning = True
        else:
            # Reset warning flag if margin recovers
            self.has_sent_margin_warning = False

    def _liquidate_all_positions(
        self, 
        current_price: float, 
        timestamp_str: str, 
        reason: str, 
        db: Optional[Session] = None
    ):
        """
        Force closes all open inventory when Margin constraints are breached.
        """
        # Trigger Stop-Out Liquidation Notification (v4.5)
        if db is not None and self.user_id is not None:
            PortfolioService.dispatch_notification(
                user_id=self.user_id,
                title="Stop Out Liquidation Triggered",
                message=f"Account liquidated. Floating margin level fell below stop out limit of {self.stop_out_level}%.",
                db=db
            )

        for pos in self.active_positions:
            # Spread cost factored into liquidations
            spread_cost = pos["entry_price"] * (self.spread_pct / 2.0)
            exit_price = current_price - spread_cost if pos["direction"] == "LONG" else current_price + spread_cost
            self._execute_close(pos, exit_price, reason, timestamp_str, db=db)
            
        self.active_positions = []
        self._recalculate_margins(current_price, db=db)

    def reset_daily_tracker(self):
        """
        Resets day-specific profit and loss thresholds.
        """
        self.daily_pnl_tracker = 0.0
        self.risk_manager.reset_daily_limits()
