# run_walk_forward.py

import os
import argparse
import pandas as pd
from walk_forward.validation_engine import WalkForwardValidator
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


def main():
    parser = argparse.ArgumentParser(
        description="Quantoryx Walk-Forward Validation Framework"
    )
    parser.add_argument(
        "--strategy", 
        type=str, 
        required=True,
        choices=["EMA", "RSI", "MACD", "BollingerBands", "Breakout", "SupportResistance", "TrendPullback"],
        help="Strategy to validate"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        required=True, 
        help="Target currency pair or ticker symbol"
    )
    parser.add_argument(
        "--timeframe", 
        type=str, 
        required=True, 
        help="Data timeframe (e.g. 1H, 4H, 1D)"
    )
    parser.add_argument(
        "--data", 
        type=str, 
        default=os.path.join("data", "EURUSD_1H.csv"),
        help="Path to historical CSV data file (default: data/EURUSD_1H.csv)"
    )
    parser.add_argument(
        "--train-days", 
        type=int, 
        default=180, 
        help="Number of days in the training/In-Sample window (default: 180)"
    )
    parser.add_argument(
        "--test-days", 
        type=int, 
        default=60, 
        help="Number of days in the testing/Out-of-Sample window (default: 60)"
    )
    parser.add_argument(
        "--metric", 
        type=str, 
        default="sharpe_ratio",
        choices=["net_profit", "profit_factor", "max_drawdown", "win_rate", "sharpe_ratio"],
        help="Optimization ranking metric (default: sharpe_ratio)"
    )

    args = parser.parse_args()

    # Initialize workspace structure
    PathManager.initialize_workspace()

    # 1. Load Data
    print(f"[+] Loading dataset from: {args.data}")
    try:
        data_df = load_historical_data(args.data)
    except Exception as e:
        print(f"[-] Error loading data: {e}")
        return

    # 2. Initialize Walk-Forward Validator
    validator = WalkForwardValidator(
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
        data_df=data_df,
        train_days=args.train_days,
        test_days=args.test_days,
        primary_metric=args.metric
    )

    # 3. Execute
    print(f"[+] Executing Walk-Forward Validation for {args.strategy} ({args.symbol} - {args.timeframe})...")
    results = validator.run_validation()

    if not results:
        print("[-] Walk-Forward Validation failed or completed with no results.")
        return

    # 4. Export results to CSV
    report_df = pd.DataFrame(results)
    report_path = PathManager.resolve_path("reports", "walk_forward_report.csv")
    report_df.to_csv(report_path, index=False)
    print(f"\n[+] Walk-forward validation results successfully exported to: {report_path}")

    # 5. Output comparative performance overview
    print("\n" + "=" * 105)
    print(" WALK-FORWARD VALIDATION SUMMARY: IN-SAMPLE (IS) VS OUT-OF-SAMPLE (OOS)")
    print("=" * 105)
    print(
        f" {'Fold':<4} | "
        f" {'IS Dates':<23} | "
        f" {'OOS Dates':<23} | "
        f" {'IS Sharpe':<9} | "
        f" {'OOS Sharpe':<10} | "
        f" {'IS Profit':<9} | "
        f" {'OOS Profit':<10}"
    )
    print("-" * 105)
    
    is_sharpes, oos_sharpes = [], []
    is_profits, oos_profits = [], []

    for row in results:
        print(
            f" {row['fold']:<4} | "
            f" {row['train_start'][:10]}..{row['train_end'][:10]} | "
            f" {row['test_start'][:10]}..{row['test_end'][:10]} | "
            f" {row['is_sharpe_ratio']:<9.2f} | "
            f" {row['oos_sharpe_ratio']:<10.2f} | "
            f" {row['is_net_profit']:<9.2f} | "
            f" {row['oos_net_profit']:<10.2f}"
        )
        is_sharpes.append(row['is_sharpe_ratio'])
        oos_sharpes.append(row['oos_sharpe_ratio'])
        is_profits.append(row['is_net_profit'])
        oos_profits.append(row['oos_net_profit'])

    # Standard aggregate performance comparison
    mean_is_sharpe = sum(is_sharpes) / len(is_sharpes) if is_sharpes else 0
    mean_oos_sharpe = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0
    total_is_profit = sum(is_profits)
    total_oos_profit = sum(oos_profits)

    print("-" * 105)
    print(
        f" {'AVG':<4} | "
        f" {'-'*23} | "
        f" {'-'*23} | "
        f" {mean_is_sharpe:<9.2f} | "
        f" {mean_oos_sharpe:<10.2f} | "
        f" {total_is_profit:<9.2f} | "
        f" {total_oos_profit:<10.2f}"
    )
    print("=" * 105 + "\n")


if __name__ == "__main__":
    main()
