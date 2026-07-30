# engine/backtest_engine.py

import os
import pandas as pd
import numpy as np
from typing import Dict, Any, List

# Core integrations
from market_regime.detector import MarketRegimeDetector
from market_regime.analyzer import MarketRegimeAnalyzer
from utils.path_manager import PathManager
from strategies import get_strategy


class BacktestEngine:
    """
    Backtesting engine representing the core simulation framework.
    Automatically tags market regimes, logs them on trade execution, 
    and outputs regime analytics reports.
    """
    # Mapping to bridge command-line names to strategies module keys
    STRATEGY_MAPPING = {
        "EMA": "ema_crossover",
        "EMACROSSOVER": "ema_crossover",
        "RSI": "rsi",
        "MACD": "macd",
        "BOLLINGERBANDS": "bollinger",
        "BOLLINGER": "bollinger",
        "BB": "bollinger",
        "BREAKOUT": "breakout",
        "SUPPORTRESISTANCE": "support_resistance",
        "SR": "support_resistance",
        "TRENDPULLBACK": "trend_pullback"
    }

    def __init__(
        self,
        data: pd.DataFrame,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        write_reports: bool = True,
    ):
        self.data = data.copy()
        self.strategy_name = strategy_name
        self.strategy_params = strategy_params
        # When False, skip per-run CSV/report writes. The optimizer sets this
        # to avoid thousands of redundant disk writes during grid search.
        self.write_reports = write_reports
        self.trades = []

        # 1. Classify market regimes for the history — but only if the caller
        #    has not already tagged the frame. Regime labels are independent of
        #    strategy parameters, so re-classifying inside every optimizer combo
        #    is pure waste; the walk-forward pipeline passes pre-tagged slices,
        #    turning an O(combos x bars) hotspot into a single upfront pass.
        self.detector = MarketRegimeDetector()
        if "market_regime" not in self.data.columns:
            self.data = self.detector.classify_regimes(self.data)

    def run(self) -> Dict[str, float]:
        """
        Runs the simulation bar-by-bar, evaluates strategy logic,
        and saves trade logs along with the automated regime report.
        """
        # Resolve strategy signals (real strategy if resolvable, else fallback)
        signals = self._generate_strategy_signals()
        
        # Pre-extract raw arrays once. Iterating over NumPy arrays instead of
        # repeated ``DataFrame.iloc[i]`` / ``index.get_loc`` lookups turns each
        # backtest from O(n) slow pandas accesses into a tight numeric loop —
        # the single biggest speedup during optimizer grid sweeps.
        index = self.data.index
        close_arr = self.data['close'].to_numpy()
        sig_arr = signals.to_numpy()
        regime_arr = self.data['market_regime'].to_numpy()

        # Simulation state
        position = None  # None, 'LONG', or 'SHORT'
        entry_price = 0.0
        entry_i = 0
        entry_time = None
        entry_regime = "Unknown"

        for i in range(len(close_arr)):
            close_price = close_arr[i]
            sig = sig_arr[i]

            if position is None:
                if sig == 1:  # Long signal
                    position = 'LONG'
                    entry_price = close_price
                    entry_i = i
                    entry_time = index[i]
                    entry_regime = regime_arr[i]
                elif sig == -1:  # Short signal
                    position = 'SHORT'
                    entry_price = close_price
                    entry_i = i
                    entry_time = index[i]
                    entry_regime = regime_arr[i]
            else:
                # Exit conditions: opposite signal or maximum 10-bar hold
                bars_held = i - entry_i
                is_exit = (position == 'LONG' and sig == -1) or \
                          (position == 'SHORT' and sig == 1) or \
                          (bars_held >= 10)

                if is_exit:
                    multiplier = 1 if position == 'LONG' else -1
                    pnl = (close_price - entry_price) * multiplier

                    # Save the trade with the registered regime
                    self.trades.append({
                        "entry_time": entry_time,
                        "exit_time": index[i],
                        "direction": position,
                        "entry_price": entry_price,
                        "exit_price": close_price,
                        "market_regime": entry_regime,  # Persisted regime
                        "pnl": pnl,
                        "net_profit": pnl
                    })
                    position = None

        # Generate and export trade logs to CSV (skipped during optimization
        # sweeps where thousands of runs would otherwise thrash the disk).
        trades_df = pd.DataFrame(self.trades)
        if not trades_df.empty and self.write_reports:
            trades_csv_name = f"trades_{self.strategy_name.lower()}.csv"
            trades_csv_path = PathManager.resolve_path("trades", trades_csv_name)
            trades_df.to_csv(trades_csv_path, index=False)
            
            # Automatically generate the market regime performance report
            analyzer = MarketRegimeAnalyzer(trades_df)
            reports_dir_path = PathManager.resolve_path("reports", "")
            analyzer.generate_regime_report(output_dir=reports_dir_path)

        # Compute standard performance metrics for engine response
        return self._calculate_metrics(trades_df)

    def _generate_strategy_signals(self) -> pd.Series:
        """
        Resolve the signal series for the configured strategy.

        Attempts to load the concrete strategy class from the ``strategies``
        package; if resolution or execution fails, falls back to a dual-EMA
        crossover so the engine always produces a well-formed signal series
        aligned to ``self.data``. This is the single public entry point used
        by both :meth:`run` and the paper-trading orchestrator.
        """
        strategy_inst = self._load_strategy()
        signals = (
            self._generate_signals(strategy_inst)
            if strategy_inst is not None
            else self._generate_fallback_signals()
        )
        # Guarantee alignment with the engine's data index.
        return signals.reindex(self.data.index).fillna(0).astype(int)

    def _load_strategy(self) -> Any:
        """
        Helper to dynamically load strategy classes from the strategies/ package.
        """
        try:
            normalized_name = self.strategy_name.upper().replace("_", "").replace(" ", "")
            strategy_key = self.STRATEGY_MAPPING.get(normalized_name)
            if strategy_key:
                return get_strategy(strategy_key, self.strategy_params)
        except Exception as e:
            print(f"[-] Warning: Failed to load strategy '{self.strategy_name}' dynamically: {e}")
        return None

    def _generate_signals(self, strategy: Any) -> pd.Series:
        """
        Helper that uses custom strategy class to generate a signal Series.
        """
        try:
            # We copy data and normalize column naming to Title Case if needed 
            # by strategy modules that expect traditional Title Case index mappings.
            df_copy = self.data.copy()
            df_copy.columns = [c.title() for c in df_copy.columns]
            
            # Attaching simulated attributes for structural compatibility
            df_copy.attrs["pair"] = "EURUSD"
            df_copy.attrs["timeframe"] = "1H"
            
            # Run preparation and signal logic
            df_prepared = strategy.run(df_copy)
            
            # Return lowercase mapped Series back to the backtester loop
            return df_prepared["Signal"] if "Signal" in df_prepared.columns else df_prepared["signal"]
        except Exception as e:
            print(f"[-] Warning: Strategy execution error. Falling back to default indicator signals: {e}")
            return self._generate_fallback_signals()

    def _generate_fallback_signals(self) -> pd.Series:
        """
        Fallback signal generator (dual EMA crossover) to ensure run() is functional.
        """
        fast_ema = self.data['close'].ewm(span=12, adjust=False).mean()
        slow_ema = self.data['close'].ewm(span=26, adjust=False).mean()
        
        signals = pd.Series(0, index=self.data.index)
        signals[fast_ema > slow_ema] = 1
        signals[fast_ema < slow_ema] = -1
        return signals

    def _calculate_metrics(self, trades_df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculates high-level metrics required by run_backtest and run_optimizer.
        """
        if trades_df.empty:
            return {
                "net_profit": 0.0,
                "profit_factor": 1.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "sharpe_ratio": 0.0
            }

        net_profit = float(trades_df['pnl'].sum())
        wins = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
        losses = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
        profit_factor = float(wins / losses) if losses > 0 else float(wins if wins > 0 else 1.0)
        
        win_rate = float(len(trades_df[trades_df['pnl'] > 0]) / len(trades_df))
        
        # Sharpe estimation assuming daily bars / proxy
        returns = trades_df['pnl']
        sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0
        
        # Max drawdown estimate
        cumulative = trades_df['pnl'].cumsum()
        running_max = cumulative.cummax()
        drawdown = cumulative - running_max
        max_drawdown = float(drawdown.min())

        return {
            "net_profit": net_profit,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe
        }
