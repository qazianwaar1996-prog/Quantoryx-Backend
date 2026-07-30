# run_optimizer.py

import os
import argparse
import pandas as pd
from typing import Optional
from optimizer.optimizer_engine import OptimizerEngine
from utils.path_manager import PathManager


def load_historical_data(file_path: str) -> Optional[pd.DataFrame]:
    """
    Loads and prepares historical market data from a CSV file.
    """
    if not os.path.exists(file_path):
        print(f"[-] Data file not found at: {file_path}")
        return None
        
    try:
        # Load CSV and enforce date column parsing
        df = pd.read_csv(file_path, parse_dates=True, index_col=0)
        # Sort index chronologically to prevent lookahead or parsing issues
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        print(f"[-] Error loading data file: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Quantoryx Parameter Optimization Module"
    )
    
    parser.add_argument(
        "--strategy", 
        type=str, 
        required=True,
        choices=["EMA", "RSI", "MACD", "BollingerBands", "Breakout", "SupportResistance", "TrendPullback"],
        help="Strategy to optimize"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        required=True, 
        help="Target currency pair or ticker (e.g., EURUSD, BTCUSD)"
    )
    parser.add_argument(
        "--timeframe", 
        type=str, 
        required=True, 
        help="Data timeframe identifier (e.g., 1H, 4H, 1D)"
    )
    parser.add_argument(
        "--data", 
        type=str, 
        default=os.path.join("data", "EURUSD_1H.csv"),
        help="Path to the historical CSV data file (default: data/EURUSD_1H.csv)"
    )
    parser.add_argument(
        "--metric", 
        type=str, 
        default="sharpe_ratio",
        choices=["net_profit", "profit_factor", "max_drawdown", "win_rate", "sharpe_ratio"],
        help="Primary ranking metric (default: sharpe_ratio)"
    )

    args = parser.parse_args()

    # Initialize workspace structure
    PathManager.initialize_workspace()

    # 1. Load historical data
    print(f"[+] Loading dataset from {args.data}...")
    data_df = load_historical_data(args.data)
    
    if data_df is None or data_df.empty:
        print("[-] Optimization aborted: Missing or invalid dataset.")
        return

    # 2. Initialize optimization runner
    optimizer = OptimizerEngine(
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
        data_df=data_df,
        primary_metric=args.metric
    )

    # 3. Execute
    try:
        ranked_results = optimizer.run_optimization()
        
        # 4. Display a brief non-assertive summary
        if ranked_results:
            best = ranked_results[0]
            print("\n" + "=" * 50)
            print(f" OPTIMIZATION SUMMARY (Rank 1 Configuration)")
            print("=" * 50)
            print(f" Strategy:     {best['strategy']}")
            print(f" Pair/TF:     {best['symbol']} ({best['timeframe']})")
            print(f" Rank Metric:  Sorted by {args.metric}")
            print("-" * 50)
            print(" Best Parameters Found:")
            for key, val in best.items():
                if key.startswith("param_"):
                    param_name = key.replace("param_", "")
                    print(f"   - {param_name}: {val}")
            print("-" * 50)
            print(" Achieved Metrics:")
            print(f"   - Net Profit:      {best['net_profit']:.2f}")
            print(f"   - Profit Factor:   {best['profit_factor']:.2f}")
            print(f"   - Max Drawdown:    {best['max_drawdown']:.2f}")
            print(f"   - Win Rate:        {best['win_rate']:.2%}")
            print(f"   - Sharpe Ratio:    {best['sharpe_ratio']:.2f}")
            print("=" * 50 + "\n")
        else:
            print("[-] Optimization finished but returned zero viable configurations.")
            
    except ImportError as ie:
        print(f"\n[-] Integration Note: {ie}")
        print("    Ensure your BacktestEngine is correctly referenced in 'optimizer/optimizer_engine.py'.")
    except Exception as e:
        print(f"[-] An unexpected error occurred during execution: {e}")


if __name__ == "__main__":
    main()
