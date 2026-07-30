# market_regime/analyzer.py

import os
import csv
import pandas as pd
from typing import List, Dict, Any, Union


class MarketRegimeAnalyzer:
    """
    Analyzes trading performance metrics across distinct market regimes
    to identify strategy strengths, weaknesses, and edge profiles.
    """
    def __init__(self, trades: Union[List[Dict[str, Any]], pd.DataFrame]):
        if isinstance(trades, pd.DataFrame):
            self.trades_df = trades.copy()
        elif isinstance(trades, list):
            self.trades_df = pd.DataFrame(trades)
        else:
            self.trades_df = pd.DataFrame()

    def generate_regime_report(self, output_dir: str = "reports") -> pd.DataFrame:
        """
        Groups trades by the entry market regime and calculates key 
        performance indicators (KPIs) for each regime.
        """
        if self.trades_df.empty:
            print("[-] No trade data found to analyze.")
            return pd.DataFrame()

        # Check required columns. Ensure consistent column naming.
        # Standardizing possible columns: 'market_regime', 'entry_regime', or 'regime'
        regime_col = None
        for col in ['market_regime', 'entry_regime', 'regime']:
            if col in self.trades_df.columns:
                regime_col = col
                break

        if not regime_col:
            # Fallback/Auto-detect if a column contains known regimes
            possible_cols = [c for c in self.trades_df.columns if self.trades_df[c].astype(str).str.contains(
                "Trending|Ranging|High Volatility|Low Volatility|Normal", na=False, regex=True
            ).any()]
            if possible_cols:
                regime_col = possible_cols[0]
            else:
                print("[-] Error: Trade data does not contain market regime classification columns.")
                return pd.DataFrame()

        # Ensure numeric types on critical metric metrics
        profit_col = 'pnl' if 'pnl' in self.trades_df.columns else ('profit' if 'profit' in self.trades_df.columns else 'net_profit')
        if profit_col not in self.trades_df.columns:
            # Fallback search
            numeric_cols = self.trades_df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                profit_col = numeric_cols[0]
            else:
                print("[-] Error: Trade data lacks numeric profit/loss columns.")
                return pd.DataFrame()

        self.trades_df[profit_col] = pd.to_numeric(self.trades_df[profit_col], errors='coerce').fillna(0.0)

        # Performance calculations grouped by regime
        grouped = self.trades_df.groupby(regime_col)
        report_data = []

        for regime, group in grouped:
            total_trades = len(group)
            if total_trades == 0:
                continue

            # Financial aggregates
            net_profit = group[profit_col].sum()
            winning_trades = group[group[profit_col] > 0]
            losing_trades = group[group[profit_col] < 0]
            
            win_count = len(winning_trades)
            loss_count = len(losing_trades)
            win_rate = win_count / total_trades if total_trades > 0 else 0.0

            # Profit Factor = Gross Profits / Abs(Gross Losses)
            gross_profit = winning_trades[profit_col].sum()
            gross_loss = abs(losing_trades[profit_col].sum())
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
            
            # Drawdown calculations within the regime subset (Max Trade PnL Drawdown)
            max_consecutive_losses = self._calculate_max_consecutive_losses(group[profit_col])
            largest_loss = group[profit_col].min()
            average_pnl = group[profit_col].mean()

            report_data.append({
                "market_regime": regime,
                "total_trades": total_trades,
                "win_rate": win_rate,
                "net_profit": net_profit,
                "profit_factor": profit_factor,
                "avg_trade_pnl": average_pnl,
                "largest_loss": largest_loss,
                "max_consecutive_losses": max_consecutive_losses
            })

        report_df = pd.DataFrame(report_data)
        
        # Save output
        if not report_df.empty:
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, "market_regime_performance.csv")
            report_df.to_csv(filepath, index=False)
            print(f"[+] Regime performance analysis report generated: {filepath}")

        return report_df

    @staticmethod
    def _calculate_max_consecutive_losses(pnl_series: pd.Series) -> int:
        """
        Helper to measure risk profile under stressful regimes.
        """
        max_consecutive = 0
        current_consecutive = 0
        
        for val in pnl_series:
            if val < 0:
                current_consecutive += 1
                if current_consecutive > max_consecutive:
                    max_consecutive = current_consecutive
            else:
                current_consecutive = 0
                
        return max_consecutive
