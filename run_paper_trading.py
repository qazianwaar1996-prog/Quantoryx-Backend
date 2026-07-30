# run_paper_trading.py

import os
import argparse
import csv
import pandas as pd
from datetime import datetime
from paper_trading.paper_engine import PaperTradingEngine
from risk.risk_manager import RiskManager
from market_regime.detector import MarketRegimeDetector
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


def generate_periodic_reports(trades: list, output_path: str = None):
    """
    Aggregates realized trade data into daily, weekly, and monthly performance buckets.
    """
    if not trades:
        print("[-] No trades recorded to construct periodic reports.")
        return

    if output_path is None:
        output_path = PathManager.resolve_path("reports", "paper_performance_report.csv")

    df = pd.DataFrame(trades)
    df['exit_time'] = pd.to_datetime(df['exit_time'])
    
    # 1. Daily Aggregations
    df['day'] = df['exit_time'].dt.strftime('%Y-%m-%d')
    daily = df.groupby('day').agg(
        total_pnl=('pnl', 'sum'),
        trade_count=('pnl', 'count'),
        wins=('pnl', lambda x: (x > 0).sum())
    ).reset_index().rename(columns={'day': 'period'})
    daily['type'] = 'DAILY'

    # 2. Weekly Aggregations
    df['week'] = df['exit_time'].dt.strftime('%Y-W%U')
    weekly = df.groupby('week').agg(
        total_pnl=('pnl', 'sum'),
        trade_count=('pnl', 'count'),
        wins=('pnl', lambda x: (x > 0).sum())
    ).reset_index().rename(columns={'week': 'period'})
    weekly['type'] = 'WEEKLY'

    # 3. Monthly Aggregations
    df['month'] = df['exit_time'].dt.strftime('%Y-%m')
    monthly = df.groupby('month').agg(
        total_pnl=('pnl', 'sum'),
        trade_count=('pnl', 'count'),
        wins=('pnl', lambda x: (x > 0).sum())
    ).reset_index().rename(columns={'month': 'period'})
    monthly['type'] = 'MONTHLY'

    # Combine all buckets
    combined_report = pd.concat([daily, weekly, monthly], ignore_index=True)
    combined_report['win_rate'] = (combined_report['wins'] / combined_report['trade_count'] * 100).round(2)
    
    # Order columns
    combined_report = combined_report[['type', 'period', 'total_pnl', 'trade_count', 'win_rate']]
    
    combined_report.to_csv(output_path, index=False)
    print(f"[+] Consolidated paper performance report generated: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Quantoryx Paper Trading Simulation Suite"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        required=True, 
        help="Target currency pair/symbol (e.g. EURUSD)"
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
        help="Initial virtual capital balance (default: 100000.0)"
    )
    parser.add_argument(
        "--leverage", 
        type=float, 
        default=30.0, 
        help="Virtual account leverage (default: 30.0)"
    )
    parser.add_argument(
        "--spread", 
        type=float, 
        default=0.0002, 
        help="Virtual transaction spread percentage (default: 0.0002)"
    )

    args = parser.parse_args()

    # Initialize workspace structure
    PathManager.initialize_workspace()

    # 1. Load Dataset
    print(f"[+] Reading historical feed from: {args.data}")
    try:
        df = load_historical_data(args.data)
    except Exception as e:
        print(f"[-] Error: {e}")
        return

    # 2. Tag Market Regimes dynamically (Phase 3 Integration)
    print("[+] Calculating indicators and tagging market regimes...")
    detector = MarketRegimeDetector()
    df_tagged = detector.classify_regimes(df)

    # 3. Instantiate Risk and Paper Trading Engines
    risk_mgr = RiskManager(
        risk_per_trade_pct=1.0,          # Risk 1.0% per trade
        max_daily_loss_pct=3.0,          # Enforce intraday cap
        max_total_drawdown_pct=10.0,     # Max account peak-to-trough drawdown
        max_concurrent_trades=3,         # Limit active exposure count
        max_exposure_per_pair_pct=15.0   # Enforce pair limit
    )
    
    paper_engine = PaperTradingEngine(
        starting_balance=args.capital,
        leverage=args.leverage,
        spread_pct=args.spread,
        risk_manager=risk_mgr
    )

    # Simple moving average to produce simulated crossover signals
    fast_ema = df_tagged['close'].ewm(span=10, adjust=False).mean()
    slow_ema = df_tagged['close'].ewm(span=30, adjust=False).mean()

    # 4. Chronological Step Feed
    print("[+] Stepping through market data feed...")
    for i in range(30, len(df_tagged)):
        timestamp = df_tagged.index[i]
        row = df_tagged.iloc[i]
        close_price = float(row['close'])
        regime = str(row['market_regime'])

        # Reset day-specific indicators
        if i > 0 and hasattr(timestamp, 'date') and timestamp.date() != df_tagged.index[i-1].date():
            paper_engine.reset_daily_tracker()

        # Update and evaluate active trades
        paper_engine.process_bar(timestamp, row, regime)

        # Signal formulation
        sig = 0
        if fast_ema.iloc[i] > slow_ema.iloc[i] and fast_ema.iloc[i-1] <= slow_ema.iloc[i-1]:
            sig = 1  # Buy
        elif fast_ema.iloc[i] < slow_ema.iloc[i] and fast_ema.iloc[i-1] >= slow_ema.iloc[i-1]:
            sig = -1 # Sell

        if sig != 0:
            direction = "LONG" if sig == 1 else "SHORT"
            paper_engine.execute_order(
                symbol=args.symbol,
                direction=direction,
                current_price=close_price,
                stop_loss_pct=1.5,
                rr_ratio=2.5,
                timestamp=timestamp,
                regime=regime
            )

    # 5. Export Logs and Reports securely via PathManager
    print("[+] Compiling transaction audit logs...")
    log_path = PathManager.resolve_path("trades", "paper_trade_log.csv")
    
    if paper_engine.trade_logs:
        log_df = pd.DataFrame(paper_engine.trade_logs)
        log_df.to_csv(log_path, index=False)
        print(f"[+] Trade execution logs exported to: {log_path}")
        
        # Periodic report generation resolved via PathManager
        perf_report_path = PathManager.resolve_path("reports", "paper_performance_report.csv")
        generate_periodic_reports(paper_engine.trade_logs, perf_report_path)
    else:
        print("[-] Skip: No trades executed during this feed simulation.")

    # Console summary output
    print("\n" + "=" * 55)
    print(" VIRTUAL PAPER TRADING ENGINE FINAL LEDGER")
    print("=" * 55)
    print(f" Starting Balance:        {args.capital:,.2f}")
    print(f" Terminal Account Balance: {paper_engine.balance:,.2f}")
    print(f" Terminal Account Equity:  {paper_engine.equity:,.2f}")
    print(f" Total Realized Trades:    {len(paper_engine.trade_logs)}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
