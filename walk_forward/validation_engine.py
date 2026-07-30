# walk_forward/validation_engine.py

import os
import pandas as pd
from typing import Dict, List, Any, Tuple
from datetime import timedelta

# Import Phase 2 Optimizer
from optimizer.optimizer_engine import OptimizerEngine
# Import Backtest Engine
from engine.backtest_engine import BacktestEngine


class WalkForwardValidator:
    """
    Coordinates Walk-Forward Validation (WFV) by rolling optimization windows (In-Sample)
    and testing parameters on subsequent unseen windows (Out-of-Sample).
    """
    def __init__(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        data_df: pd.DataFrame,
        train_days: int = 180,
        test_days: int = 60,
        primary_metric: str = "sharpe_ratio"
    ):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.timeframe = timeframe
        self.data_df = data_df.copy()
        self.train_days = train_days
        self.test_days = test_days
        self.primary_metric = primary_metric

        # Ensure datetime index is correctly prepared
        if not isinstance(self.data_df.index, pd.DatetimeIndex):
            self.data_df.index = pd.to_datetime(self.data_df.index)
        self.data_df.sort_index(inplace=True)

    def generate_windows(self) -> List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
        """
        Calculates non-overlapping testing windows preceded by rolling training windows.
        Returns a list of tuples: (train_start, train_end, test_start, test_end)
        """
        windows = []
        first_date = self.data_df.index[0]
        last_date = self.data_df.index[-1]
        
        # We step through the dataset in intervals equal to test_days
        current_test_start = first_date + timedelta(days=self.train_days)
        
        while current_test_start + timedelta(days=self.test_days) <= last_date:
            train_start = current_test_start - timedelta(days=self.train_days)
            train_end = current_test_start - timedelta(seconds=1)
            
            test_start = current_test_start
            test_end = current_test_start + timedelta(days=self.test_days) - timedelta(seconds=1)
            
            windows.append((train_start, train_end, test_start, test_end))
            
            # Step forward
            current_test_start += timedelta(days=self.test_days)
            
        return windows

    def run_validation(self) -> List[Dict[str, Any]]:
        """
        Executes the walk-forward validation matrix across all generated windows.
        """
        windows = self.generate_windows()
        if not windows:
            print("[-] Insufficient historical data length to construct validation windows.")
            return []

        print(f"[+] Constructed {len(windows)} walk-forward windows.")
        results = []

        for fold, (train_start, train_end, test_start, test_end) in enumerate(windows, 1):
            print(f"\n--- Processing Fold {fold}/{len(windows)} ---")
            print(f"    Train (In-Sample):  {train_start.date()} to {train_end.date()}")
            print(f"    Test (Out-of-Sample): {test_start.date()} to {test_end.date()}")

            # Slice the data
            train_data = self.data_df.loc[train_start:train_end]
            test_data = self.data_df.loc[test_start:test_end]

            if len(train_data) < 10 or len(test_data) < 10:
                print(f"    [-] Fold {fold} skipped due to insufficient bar counts in slice.")
                continue

            # 1. Optimize on In-Sample (Training) data
            optimizer = OptimizerEngine(
                strategy_name=self.strategy_name,
                symbol=self.symbol,
                timeframe=self.timeframe,
                data_df=train_data,
                primary_metric=self.primary_metric
            )
            
            # Run grid optimization
            print(f"    [+] Running optimization on In-Sample window...")
            ranked_runs = optimizer.run_optimization()
            
            if not ranked_runs:
                print(f"    [-] Optimization failed to find valid parameter sets for Fold {fold}.")
                continue
                
            # Extract the best parameters identified
            best_run = ranked_runs[0]
            best_params = {}
            for k, v in best_run.items():
                if k.startswith("param_"):
                    best_params[k.replace("param_", "")] = v

            print(f"    [+] Selected Best In-Sample Params: {best_params}")

            # 2. Run Backtest with Best Params on Out-of-Sample (Testing) data
            print(f"    [+] Evaluating chosen parameters on Out-of-Sample window...")
            test_engine = BacktestEngine(
                data=test_data,
                strategy_name=self.strategy_name,
                strategy_params=best_params
            )
            oos_metrics = test_engine.run()

            # Record aggregated details
            fold_results = {
                "fold": fold,
                "train_start": train_start.date().isoformat(),
                "train_end": train_end.date().isoformat(),
                "test_start": test_start.date().isoformat(),
                "test_end": test_end.date().isoformat(),
                "parameters": str(best_params),
                
                # In-Sample (IS) Metrics
                "is_net_profit": best_run.get("net_profit", 0.0),
                "is_profit_factor": best_run.get("profit_factor", 0.0),
                "is_max_drawdown": best_run.get("max_drawdown", 0.0),
                "is_win_rate": best_run.get("win_rate", 0.0),
                "is_sharpe_ratio": best_run.get("sharpe_ratio", 0.0),
                
                # Out-of-Sample (OOS) Metrics
                "oos_net_profit": oos_metrics.get("net_profit", 0.0),
                "oos_profit_factor": oos_metrics.get("profit_factor", 0.0),
                "oos_max_drawdown": oos_metrics.get("max_drawdown", 0.0),
                "oos_win_rate": oos_metrics.get("win_rate", 0.0),
                "oos_sharpe_ratio": oos_metrics.get("sharpe_ratio", 0.0),
            }
            results.append(fold_results)

        return results
