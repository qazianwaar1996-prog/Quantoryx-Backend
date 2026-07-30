# portfolio/portfolio_manager.py

import os
import csv
import pandas as pd
import numpy as np
from typing import Dict, List, Any

# Core integration
from utils.path_manager import PathManager


class PortfolioManager:
    """
    Manages portfolio-level capital tracking, daily equity snapshots, 
    risk metrics (Sharpe, Peak-to-Trough Drawdown), and report compilation.
    """
    def __init__(self, starting_balance: float = 100000.0):
        self.starting_balance = starting_balance
        self.current_balance = starting_balance
        self.current_equity = starting_balance
        
        # Chronological series logs
        self.equity_curve: List[Dict[str, Any]] = []  # List of {"date": str, "equity": float, "drawdown_pct": float}
        self.trade_history: List[Dict[str, Any]] = []
        
        # State trackers
        self.peak_equity = starting_balance
        self.current_drawdown_pct = 0.0
        self.max_drawdown_pct = 0.0

    def record_snapshot(self, date_str: str, unrealized_pnl: float = 0.0):
        """
        Takes an end-of-day or bar snapshot of account equity and calculates drawdowns.
        """
        self.current_equity = self.current_balance + unrealized_pnl
        
        # Update peaks and drawdowns
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
            
        drawdown_amount = self.peak_equity - self.current_equity
        self.current_drawdown_pct = drawdown_amount / self.peak_equity if self.peak_equity > 0 else 0.0
        
        if self.current_drawdown_pct > self.max_drawdown_pct:
            self.max_drawdown_pct = self.current_drawdown_pct
            
        self.equity_curve.append({
            "date": date_str,
            "balance": round(self.current_balance, 2),
            "equity": round(self.current_equity, 2),
            "drawdown_pct": round(self.current_drawdown_pct * 100, 4)
        })

    def process_realized_trade(self, trade: Dict[str, Any]):
        """
        Applies a completed trade's net profit/loss to the cash balance.
        """
        realized_pnl = trade.get("pnl", 0.0)
        self.current_balance += realized_pnl
        self.trade_history.append(trade)

    def calculate_portfolio_metrics(self) -> Dict[str, Any]:
        """
        Computes global KPIs based on completed trades and the historical equity curve.
        """
        if not self.equity_curve:
            return {}

        df_curve = pd.DataFrame(self.equity_curve)
        
        # Total Return
        total_return_pct = ((self.current_equity - self.starting_balance) / self.starting_balance) * 100.0
        
        # Daily Returns & Sharpe Ratio calculation
        # Sharpe = (Average Daily Return / Std Dev of Daily Returns) * Sqrt(252)
        df_curve['daily_return'] = df_curve['equity'].pct_change().fillna(0.0)
        mean_return = df_curve['daily_return'].mean()
        std_return = df_curve['daily_return'].std()
        
        annualized_sharpe = 0.0
        if std_return > 0:
            annualized_sharpe = (mean_return / std_return) * np.sqrt(252)

        # Win/Loss ratios
        pnl_list = [t.get("pnl", 0.0) for t in self.trade_history]
        total_trades = len(pnl_list)
        winning_trades = [p for p in pnl_list if p > 0]
        losing_trades = [p for p in pnl_list if p < 0]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
        gross_profit = sum(winning_trades)
        gross_loss = abs(sum(losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        return {
            "starting_balance": self.starting_balance,
            "ending_equity": self.current_equity,
            "total_return_pct": round(total_return_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct * 100, 2),
            "sharpe_ratio": round(annualized_sharpe, 2),
            "total_trades": total_trades,
            "win_rate": round(win_rate * 100, 2),
            "profit_factor": round(profit_factor, 2),
            "net_profit": round(self.current_equity - self.starting_balance, 2)
        }

    def export_portfolio_report(self, filepath: str = None):
        """
        Exports the chronologically logged equity data to CSV.
        """
        if not self.equity_curve:
            return

        # Automatically route path using PathManager if no specific override is given
        if filepath is None:
            filepath = PathManager.resolve_path("reports", "portfolio_report.csv")

        fieldnames = ["date", "balance", "equity", "drawdown_pct"]
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.equity_curve)

        print(f"[+] Portfolio report successfully exported to: {filepath}")
