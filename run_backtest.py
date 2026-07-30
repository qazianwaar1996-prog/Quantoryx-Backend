# run_backtest.py

import os
import argparse
import pandas as pd
from typing import Optional
from engine.backtest_engine import BacktestEngine
from utils.path_manager import PathManager


def load_dataset(file_path: str) -> Optional[pd.DataFrame]:
    """
    Safely loads and parses the historical market data.
    """
    if not os.path.exists(file_path):
        print(f"[-] Dataset file not found at: {file_path}")
        return None
    try:
        df = pd.read_csv(file_path, parse_dates=True, index_col=0)
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        print(f"[-] Failed to read historical dataset: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Quantoryx Backtesting Simulation Engine"
    )
    parser.add_argument(
        "--strategy", 
        type=str, 
        required=True,
        help="Strategy to simulate (e.g. EMA, RSI, MACD, BollingerBands)"
    )
    parser.add_argument(
        "--data", 
        type=str, 
        default=os.path.join("data", "EURUSD_1H.csv"),
        help="Path to the historical OHLCV CSV file (default: data/EURUSD_1H.csv)"
    )
    parser.add_argument(
        "--fast-period", 
        type=int, 
        default=12, 
        help="Fast window parameter for calculation overrides"
    )
    parser.add_argument(
        "--slow-period", 
        type=int, 
        default=26, 
        help="Slow window parameter for calculation overrides"
    )

    args = parser.parse_args()

    # Initialize workspace structure
    PathManager.initialize_workspace()

    # 1. Load data
    print(f"[+] Launching backtest pipeline for: {args.strategy}")
    df = load_dataset(args.data)
    if df is None or df.empty:
        print("[-] Backtest execution halted.")
        return

    # Pack strategy parameters dynamically
    strategy_params = {
        "fast_period": args.fast_period,
        "slow_period": args.slow_period
    }

    # 2. Instantiate and run the upgraded BacktestEngine
    # The regime classification and performance reporting run automatically inside
    engine = BacktestEngine(
        data=df,
        strategy_name=args.strategy,
        strategy_params=strategy_params
    )

    print("[+] Simulating trade execution sequences...")
    metrics = engine.run()

    # 3. Print high-level metrics summary
    print("\n" + "=" * 50)
    print(" BACKTEST PERFORMANCE OVERVIEW (QUANTORYX)")
    print("=" * 50)
    print(f" Strategy Name:    {args.strategy}")
    print(f" Total Net Profit: {metrics['net_profit']:.2f}")
    print(f" Profit Factor:    {metrics['profit_factor']:.2f}")
    print(f" Max Drawdown:     {metrics['max_drawdown']:.2f}")
    print(f" Win Rate:         {metrics['win_rate']:.2%}")
    print(f" Sharpe Ratio:     {metrics['sharpe_ratio']:.2f}")
    print("=" * 50)
    print("[+] Process completed. Check the 'reports/' and 'output/' directories.")


if __name__ == "__main__":
    main()
