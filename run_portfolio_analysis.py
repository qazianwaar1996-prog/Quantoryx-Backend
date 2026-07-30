# run_portfolio_analysis.py

import os
import argparse
import csv
import pandas as pd
from datetime import datetime

import config
from risk.risk_manager import RiskManager
from portfolio.portfolio_manager import PortfolioManager
from utils.path_manager import PathManager


def load_historical_data(file_path: str) -> pd.DataFrame:
    """
    Loads historical market data from a CSV file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Data file not found at: {file_path}")
    
    df = pd.read_csv(file_path, parse_dates=True, index_col=0)
    df.sort_index(inplace=True)
    return df


def simulate_portfolio_simulation(
    df: pd.DataFrame,
    symbol: str,
    risk_mgr: RiskManager,
    portfolio_mgr: PortfolioManager,
    stop_loss_pct: float,
    rr_ratio: float
) -> list:
    """
    Simulates trading with fully integrated risk controls, dynamic sizing, 
    and concurrent/exposure constraint tracking.
    """
    risk_logs = []
    active_positions = []
    
    # Standard signal generation (using a basic dual EMA crossover as signal source)
    fast_ema = df['close'].ewm(span=10, adjust=False).mean()
    slow_ema = df['close'].ewm(span=30, adjust=False).mean()
    
    for i in range(30, len(df)):
        timestamp = df.index[i]
        close_price = df['close'].iloc[i]
        date_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(timestamp, 'strftime') else str(timestamp)
        
        # 1. Update Portfolio Snapshot at start of step
        unrealized_pnl = 0.0
        for pos in active_positions:
            mult = 1 if pos["direction"] == "LONG" else -1
            unrealized_pnl += (close_price - pos["entry_price"]) * pos["size"] * mult
            
        portfolio_mgr.record_snapshot(date_str, unrealized_pnl=unrealized_pnl)
        
        # Sync risk manager state from portfolio data
        risk_mgr.account_drawdown_pct = portfolio_mgr.current_drawdown_pct
        risk_mgr.active_trades_count = len(active_positions)
        
        # 2. Check for Exits on Active Positions
        remaining_positions = []
        for pos in active_positions:
            is_exit = False
            exit_reason = "Signal Exit"
            mult = 1 if pos["direction"] == "LONG" else -1
            
            # Hit Stop Loss?
            if (pos["direction"] == "LONG" and close_price <= pos["stop_loss"]) or \
               (pos["direction"] == "SHORT" and close_price >= pos["stop_loss"]):
                is_exit = True
                close_price = pos["stop_loss"]  # Fill at stop price for simulation accuracy
                exit_reason = "Stop Loss Hit"
                
            # Hit Take Profit?
            elif (pos["direction"] == "LONG" and close_price >= pos["take_profit"]) or \
                 (pos["direction"] == "SHORT" and close_price <= pos["take_profit"]):
                is_exit = True
                close_price = pos["take_profit"]  # Fill at target price
                exit_reason = "Take Profit Hit"
                
            # Trend Reverse?
            elif (pos["direction"] == "LONG" and fast_ema.iloc[i] < slow_ema.iloc[i]) or \
                 (pos["direction"] == "SHORT" and fast_ema.iloc[i] > slow_ema.iloc[i]):
                is_exit = True
                exit_reason = "Crossover Reverse"
                
            if is_exit:
                trade_pnl = (close_price - pos["entry_price"]) * pos["size"] * mult
                pos["exit_price"] = close_price
                pos["exit_time"] = date_str
                pos["pnl"] = trade_pnl
                
                # Realize the trade outcome in our tracking systems
                portfolio_mgr.process_realized_trade(pos)
                margin_exposure = pos.get("margin", pos["entry_price"] * pos["size"] / config.DEFAULT_LEVERAGE)
                risk_mgr.register_trade_close(symbol, notional_size=margin_exposure, realized_pnl=trade_pnl)
                
                risk_logs.append({
                    "timestamp": date_str,
                    "event": "TRADE_CLOSED",
                    "symbol": symbol,
                    "direction": pos["direction"],
                    "size": pos["size"],
                    "entry_price": pos["entry_price"],
                    "exit_price": close_price,
                    "pnl": round(trade_pnl, 2),
                    "reason": exit_reason
                })
            else:
                remaining_positions.append(pos)
                
        active_positions = remaining_positions
        
        # Reset daily risk metrics at day boundary transitions
        if i > 0 and hasattr(timestamp, 'date') and timestamp.date() != df.index[i-1].date():
            risk_mgr.reset_daily_limits()

        # 3. Evaluate Signal Entries
        sig = 0
        if fast_ema.iloc[i] > slow_ema.iloc[i] and fast_ema.iloc[i-1] <= slow_ema.iloc[i-1]:
            sig = 1  # Long Signal
        elif fast_ema.iloc[i] < slow_ema.iloc[i] and fast_ema.iloc[i-1] >= slow_ema.iloc[i-1]:
            sig = -1  # Short Signal
            
        if sig != 0 and len(active_positions) < risk_mgr.max_concurrent_trades:
            direction = "LONG" if sig == 1 else "SHORT"
            
            # Generate Stop Loss and Take Profit
            sl_price, tp_price = risk_mgr.calculate_sl_tp(
                direction=direction,
                entry_price=close_price,
                stop_loss_pct=stop_loss_pct,
                rr_ratio=rr_ratio
            )
            
            # Calculate dynamic position sizing (units)
            size = risk_mgr.calculate_position_size(
                balance=portfolio_mgr.current_balance,
                entry_price=close_price,
                stop_loss_price=sl_price
            )
            
            if size > 0:
                # Exposure is tracked as committed margin (notional / leverage),
                # consistent with the paper-trading engine, so the per-pair
                # exposure gate is tradable on a leveraged account.
                proposed_notional = close_price * size
                proposed_margin = proposed_notional / config.DEFAULT_LEVERAGE

                # Verify compliance against all portfolio risk gates
                approved, verdict = risk_mgr.evaluate_entry_allowance(
                    symbol=symbol,
                    balance=portfolio_mgr.current_balance,
                    current_drawdown_pct=portfolio_mgr.current_drawdown_pct,
                    daily_loss_amount=risk_mgr.daily_accumulated_loss,
                    proposed_notional_size=proposed_margin
                )
                
                if approved:
                    # Commit position
                    pos_data = {
                        "entry_time": date_str,
                        "direction": direction,
                        "entry_price": close_price,
                        "size": size,
                        "stop_loss": sl_price,
                        "take_profit": tp_price
                    }
                    pos_data["margin"] = proposed_margin
                    active_positions.append(pos_data)
                    risk_mgr.register_trade_open(symbol, notional_size=proposed_margin)
                    
                    risk_logs.append({
                        "timestamp": date_str,
                        "event": "TRADE_OPENED",
                        "symbol": symbol,
                        "direction": direction,
                        "size": size,
                        "entry_price": close_price,
                        "exit_price": "",
                        "pnl": "",
                        "reason": f"SL: {sl_price} | TP: {tp_price}"
                    })
                else:
                    risk_logs.append({
                        "timestamp": date_str,
                        "event": "TRADE_REJECTED",
                        "symbol": symbol,
                        "direction": direction,
                        "size": size,
                        "entry_price": close_price,
                        "exit_price": "",
                        "pnl": "",
                        "reason": verdict
                    })
                    
    return risk_logs


def export_risk_report(logs: list, filepath: str = None):
    """
    Exports documented risk occurrences and size decisions to a CSV log.
    """
    if not logs:
        return
    
    # Standardize output path via PathManager
    if filepath is None:
        filepath = PathManager.resolve_path("reports", "risk_report.csv")
        
    fieldnames = ["timestamp", "event", "symbol", "direction", "size", "entry_price", "exit_price", "pnl", "reason"]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(logs)
        
    print(f"[+] Risk management report successfully exported to: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description="Quantoryx Risk & Portfolio Management Suite"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        required=True, 
        help="Target currency pair or symbol"
    )
    parser.add_argument(
        "--data", 
        type=str, 
        default=os.path.join("data", "EURUSD_1H.csv"),
        help="Path to the historical CSV data file (default: data/EURUSD_1H.csv)"
    )
    parser.add_argument(
        "--capital", 
        type=float, 
        default=100000.0, 
        help="Starting capital allocation (default: 100000.0)"
    )
    parser.add_argument(
        "--risk-pct", 
        type=float, 
        default=1.0, 
        help="Max account balance risk percentage per trade (default: 1.0%%)"
    )
    parser.add_argument(
        "--stop-loss-pct", 
        type=float, 
        default=1.5, 
        help="Stop loss percent distance from entry (default: 1.5%%)"
    )
    parser.add_argument(
        "--rr-ratio", 
        type=float, 
        default=2.5, 
        help="Target Risk:Reward multiplier (default: 2.5)"
    )

    args = parser.parse_args()

    # Initialize workspace structure
    PathManager.initialize_workspace()

    # 1. Load Dataset
    print(f"[+] Loading historical data from: {args.data}")
    try:
        df = load_historical_data(args.data)
    except Exception as e:
        print(f"[-] Error: {e}")
        return

    # 2. Instantiate Managers
    risk_mgr = RiskManager(
        risk_per_trade_pct=args.risk_pct,
        max_daily_loss_pct=3.0,
        max_total_drawdown_pct=10.0,
        max_concurrent_trades=2,
        max_exposure_per_pair_pct=15.0
    )
    portfolio_mgr = PortfolioManager(starting_balance=args.capital)

    # 3. Execute Simulation
    print("[+] Starting transaction simulation with dynamic risk allocations...")
    risk_logs = simulate_portfolio_simulation(
        df=df,
        symbol=args.symbol,
        risk_mgr=risk_mgr,
        portfolio_mgr=portfolio_mgr,
        stop_loss_pct=args.stop_loss_pct,
        rr_ratio=args.rr_ratio
    )

    # 4. Export Reports securely via PathManager
    risk_report_path = PathManager.resolve_path("reports", "risk_report.csv")
    portfolio_report_path = PathManager.resolve_path("reports", "portfolio_report.csv")
    
    export_risk_report(risk_logs, filepath=risk_report_path)
    portfolio_mgr.export_portfolio_report(filepath=portfolio_report_path)

    # 5. Output Summary Results
    metrics = portfolio_mgr.calculate_portfolio_metrics()
    if metrics:
        print("\n" + "=" * 65)
        print(" INTEGRATED PORTFOLIO ANALYSIS SUMMARY (QUANTORYX)")
        print("=" * 65)
        print(f" Initial Allocation:      {metrics['starting_balance']:,.2f}")
        print(f" Terminal Equity:          {metrics['ending_equity']:,.2f}")
        print(f" Cumulative Return:        {metrics['total_return_pct']:.2f}%")
        print(f" Maximum Peak-to-Trough DD: {metrics['max_drawdown_pct']:.2f}%")
        print(f" Annualized Sharpe Ratio:  {metrics['sharpe_ratio']:.2f}")
        print(f" Total Trades Registered:  {metrics['total_trades']}")
        print(f" Win Rate Coefficient:     {metrics['win_rate']:.2f}%")
        print(f" Profit Factor:            {metrics['profit_factor']:.2f}")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
