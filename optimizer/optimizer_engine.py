# optimizer/optimizer_engine.py

import os
import csv
import json
import importlib
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import parameter range generation
from optimizer.param_ranges import generate_combinations

# We assume a standard imports/architecture for the QuantPilot framework.
# If your backtest engine is named differently, adjust the import path below.
try:
    from engine.backtest_engine import BacktestEngine
except ImportError:
    # Fallback to allow modular standalone testing or custom imports
    BacktestEngine = None


class OptimizerEngine:
    """
    Handles systematic grid-search optimization across historical datasets.
    Ranks combinations based on 5 quantitative metrics and exports results.
    """
    def __init__(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        data_df: pd.DataFrame,
        custom_ranges: Optional[Dict[str, List[Any]]] = None,
        primary_metric: str = "sharpe_ratio"
    ):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.timeframe = timeframe
        self.data_df = data_df
        self.custom_ranges = custom_ranges
        self.primary_metric = primary_metric
        
        # Output directory setup
        self.output_dir = os.path.join("output", "optimization")
        os.makedirs(self.output_dir, exist_ok=True)

    def run_optimization(self) -> List[Dict[str, Any]]:
        """
        Executes grid search over generated parameter combinations.
        """
        # 1. Generate combinations
        combos = generate_combinations(self.strategy_name, self.custom_ranges)
        if not combos:
            print(f"[-] No valid parameter combinations generated for {self.strategy_name}.")
            return []

        print(f"[+] Starting optimization for {self.strategy_name} ({self.symbol} - {self.timeframe})")
        print(f"[+] Testing {len(combos)} parameter combinations...")

        raw_results = []

        # 2. Iterate and evaluate
        for i, params in enumerate(combos, 1):
            try:
                # Call backtester
                metrics = self._execute_backtest(params)
                
                # Merge parameters and performance results
                result_row = {
                    "strategy": self.strategy_name,
                    "symbol": self.symbol,
                    "timeframe": self.timeframe,
                    **{f"param_{k}": v for k, v in params.items()},
                    "net_profit": metrics.get("net_profit", 0.0),
                    "profit_factor": metrics.get("profit_factor", 0.0),
                    "max_drawdown": metrics.get("max_drawdown", 0.0),
                    "win_rate": metrics.get("win_rate", 0.0),
                    "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
                }
                raw_results.append(result_row)
                
                if i % max(1, len(combos) // 10) == 0 or i == len(combos):
                    print(f"    Progress: {i}/{len(combos)} combinations processed.")
            except Exception as e:
                print(f"[-] Error evaluating combination {params}: {e}")

        if not raw_results:
            return []

        # 3. Rank the results
        ranked_results = self._rank_results(raw_results)
        
        # 4. Save results to CSV
        self._export_to_csv(ranked_results)
        
        # 5. Save the single best setup
        if ranked_results:
            self._save_best_config(ranked_results[0])

        return ranked_results

    def _execute_backtest(self, params: Dict[str, Any]) -> Dict[str, float]:
        """
        Adapts to the framework's BacktestEngine. 
        If running standalone/missing engine import, it simulates a run for testing.
        """
        if BacktestEngine is not None:
            # Standard QuantPilot initialization
            # Adjust these arguments to fit your engine's exact instantiation signature
            engine = BacktestEngine(
                data=self.data_df,
                strategy_name=self.strategy_name,
                strategy_params=params,
                write_reports=False,  # grid search: skip redundant per-run disk writes
            )
            results = engine.run()
            
            # Format return metrics to standard float expectations
            return {
                "net_profit": float(results.get("net_profit", 0.0)),
                "profit_factor": float(results.get("profit_factor", 1.0)),
                "max_drawdown": float(results.get("max_drawdown", 0.0)),
                "win_rate": float(results.get("win_rate", 0.0)),
                "sharpe_ratio": float(results.get("sharpe_ratio", 0.0)),
            }
        else:
            # Standalone placeholder to prevent execution crashes if run out-of-context
            raise ImportError(
                "BacktestEngine could not be imported. "
                "Verify the module path in `optimizer/optimizer_engine.py` matches your engine file."
            )

    def _rank_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ranks parameter results using a multi-metric sorting approach.
        Drawdown values are assumed to be negative or positive; we handle 
        them by sorting to minimize absolute drawdown (closer to zero is better).
        """
        # Determine sorting keys
        # Lower drawdown is better (absolute value closest to 0)
        # Higher values for all other metrics are better
        
        def rank_score(item):
            # Normalizing individual metrics into ordinal rank index or sorting directly
            # We sort primarily by the selected primary_metric, with fallback metrics to break ties.
            
            # Extract metrics
            net_profit = item.get("net_profit", 0.0)
            profit_factor = item.get("profit_factor", 0.0)
            win_rate = item.get("win_rate", 0.0)
            sharpe = item.get("sharpe_ratio", 0.0)
            
            # Maximize positive metrics; minimize drawdown
            # (using abs to handle positive or negative representations of drawdown)
            drawdown = abs(item.get("max_drawdown", 0.0))
            
            # Map metric names to sorting priorities
            metrics_map = {
                "net_profit": net_profit,
                "profit_factor": profit_factor,
                "max_drawdown": -drawdown,  # negative so larger is closer to 0
                "win_rate": win_rate,
                "sharpe_ratio": sharpe
            }
            
            # Primary choice at front of tuple, followed by backup indicators
            primary_val = metrics_map.get(self.primary_metric, sharpe)
            
            return (
                primary_val,
                sharpe,
                net_profit,
                profit_factor,
                -drawdown,
                win_rate
            )

        # Sort descending (highest rank tuple first)
        ranked = sorted(results, key=rank_score, reverse=True)
        
        # Assign numeric ranks
        for rank, item in enumerate(ranked, 1):
            item["rank"] = rank
            
        return ranked

    def _export_to_csv(self, ranked_results: List[Dict[str, Any]]):
        """
        Exports all evaluated combinations to a CSV report.
        """
        filename = f"opt_{self.strategy_name}_{self.symbol}_{self.timeframe}.csv".lower()
        filepath = os.path.join(self.output_dir, filename)
        
        if not ranked_results:
            return

        # Dynamically determine headers (handling differing parameter keys)
        headers = ["rank", "strategy", "symbol", "timeframe"]
        param_headers = [k for k in ranked_results[0].keys() if k.startswith("param_")]
        metric_headers = ["net_profit", "profit_factor", "max_drawdown", "win_rate", "sharpe_ratio"]
        
        fieldnames = headers + param_headers + metric_headers

        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(ranked_results)

        print(f"[+] Full optimization results saved to: {filepath}")

    def _save_best_config(self, best_result: Dict[str, Any]):
        """
        Persists the single best set of configurations for the specific strategy,
        symbol, and timeframe context.
        """
        config_dir = os.path.join("config", "optimized")
        os.makedirs(config_dir, exist_ok=True)
        
        # Extract parameter keys without 'param_' prefix
        best_params = {}
        for k, v in best_result.items():
            if k.startswith("param_"):
                original_key = k.replace("param_", "")
                best_params[original_key] = v

        meta_data = {
            "strategy": best_result["strategy"],
            "symbol": best_result["symbol"],
            "timeframe": best_result["timeframe"],
            "optimized_at": datetime.now().isoformat(),
            "best_parameters": best_params,
            "metrics": {
                "net_profit": best_result["net_profit"],
                "profit_factor": best_result["profit_factor"],
                "max_drawdown": best_result["max_drawdown"],
                "win_rate": best_result["win_rate"],
                "sharpe_ratio": best_result["sharpe_ratio"]
            }
        }

        filename = f"best_{self.strategy_name}_{self.symbol}_{self.timeframe}.json".lower()
        filepath = os.path.join(config_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=4)

        print(f"[+] Best parameters configuration saved to: {filepath}")
