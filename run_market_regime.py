# run_market_regime.py

import os
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from market_regime.detector import MarketRegimeDetector
from market_regime.analyzer import MarketRegimeAnalyzer
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


def simulate_sample_trades_with_regimes(df_tagged: pd.DataFrame) -> pd.DataFrame:
    """
    Helper function to generate a set of deterministic sample trades based on 
    a basic crossover to demonstrate the integration of the regime detector 
    with the backtester.
    """
    trades = []
    position = None
    
    # Simple moving average to generate mock signals
    short_ma = df_tagged['close'].rolling(window=10).mean()
    long_ma = df_tagged['close'].rolling(window=30).mean()
    
    for i in range(30, len(df_tagged)):
        timestamp = df_tagged.index[i]
        close_price = df_tagged['close'].iloc[i]
        regime = df_tagged['market_regime'].iloc[i]
        
        # Simple signal crossover
        if position is None:
            if short_ma.iloc[i] > long_ma.iloc[i] and short_ma.iloc[i-1] <= long_ma.iloc[i-1]:
                # Enter Long
                position = {
                    "entry_time": timestamp,
                    "entry_price": close_price,
                    "market_regime": regime  # Recorded at time of trade entry
                }
        else:
            # Simple Exit (after 5 bars or crossover reverse)
            bars_held = i - df_tagged.index.get_loc(position["entry_time"])
            if bars_held >= 5 or (short_ma.iloc[i] < long_ma.iloc[i]):
                pnl = close_price - position["entry_price"]
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": timestamp,
                    "entry_price": position["entry_price"],
                    "exit_price": close_price,
                    "market_regime": position["market_regime"],  # Persisted entry regime
                    "pnl": pnl
                })
                position = None
                
    return pd.DataFrame(trades)


def main():
    parser = argparse.ArgumentParser(
        description="Quantoryx Market Regime Classification & Analysis Utility"
    )
    parser.add_argument(
        "--data", 
        type=str, 
        default=os.path.join("data", "EURUSD_1H.csv"),
        help="Path to historical OHLCV CSV file (default: data/EURUSD_1H.csv)"
    )
    parser.add_argument(
        "--trades", 
        type=str, 
        default=None, 
        help="Optional path to an existing trades.csv file from a backtest run"
    )

    args = parser.parse_args()

    # Initialize workspace structure
    PathManager.initialize_workspace()

    # 1. Load Data
    print(f"[+] Loading dataset from: {args.data}")
    try:
        df = load_historical_data(args.data)
    except Exception as e:
        print(f"[-] Error loading data: {e}")
        return

    # 2. Run Regime Detection
    print("[+] Calculating indicators and classifying market regimes...")
    detector = MarketRegimeDetector()
    df_tagged = detector.classify_regimes(df)

    # Save tagged file through central PathManager
    tagged_file_path = PathManager.resolve_path("output", "market_data_regimes.csv")
    df_tagged.to_csv(tagged_file_path)
    print(f"[+] Tagged market data exported to: {tagged_file_path}")

    # Display dataset distribution summary
    total_valid = len(df_tagged[df_tagged['market_regime'] != 'Unknown'])
    print("\n--- Market Regime Distribution Summary (Quantoryx) ---")
    if total_valid > 0:
        counts = df_tagged['market_regime'].value_counts()
        for regime, count in counts.items():
            pct = (count / len(df_tagged)) * 100
            print(f"  {regime:<20}: {count:>5} bars ({pct:.2f}%)")
    else:
        print("  No classified regimes found (insufficient data warmup).")
    print("-" * 42 + "\n")

    # 3. Process Performance Report
    trades_df = pd.DataFrame()
    
    if args.trades and os.path.exists(args.trades):
        print(f"[+] Processing existing trades from: {args.trades}")
        try:
            trades_df = pd.read_csv(args.trades)
        except Exception as e:
            print(f"[-] Failed to load trades file: {e}")
    else:
        # Generate simulation trades if no external file is supplied
        print("[+] No trades file provided. Generating a trade simulation loop to test analyzer...")
        trades_df = simulate_sample_trades_with_regimes(df_tagged)
        print(f"[+] Generated {len(trades_df)} simulation trades.")

    if not trades_df.empty:
        # Run analyzer report and resolve target directory
        print("[+] Compiling strategy performance per market regime...")
        analyzer = MarketRegimeAnalyzer(trades_df)
        reports_dir = PathManager.resolve_path("reports", "")
        report_df = analyzer.generate_regime_report(output_dir=reports_dir)

        # Print clean console output of the report
        if not report_df.empty:
            print("\n" + "=" * 80)
            print(" REGIME PERFORMANCE KPI REPORT (QUANTORYX)")
            print("=" * 80)
            print(f" {'Market Regime':<18} | {'Trades':<6} | {'Win Rate':<8} | {'Net Profit':<10} | {'Profit Factor':<13} | {'Avg PnL':<8}")
            print("-" * 80)
            for _, row in report_df.iterrows():
                print(
                    f" {row['market_regime']:<18} | "
                    f" {row['total_trades']:<6} | "
                    f" {row['win_rate']:<8.2%} | "
                    f" {row['net_profit']:<10.2f} | "
                    f" {row['profit_factor']:<13.2f} | "
                    f" {row['avg_trade_pnl']:<8.2f}"
                )
            print("=" * 80 + "\n")
    else:
        print("[-] Skip: No trade data was processed.")


if __name__ == "__main__":
    main()
