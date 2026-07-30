# run_ai_engine.py

import os
import argparse
import csv
import pandas as pd
from datetime import datetime
from ai_engine.decision_engine import AIDecisionEngine
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


def generate_mock_wfv_summaries() -> list:
    """
    Generates a realistic set of Walk-Forward validation outputs for 
    the 7 strategies to feed into the selection matrix.
    """
    return [
        {
            "strategy": "EMA",
            "avg_oos_sharpe": 1.15,
            "avg_oos_win_rate": 0.54,
            "avg_oos_profit_factor": 1.35,
            "active_params": {"fast_period": 10, "slow_period": 30}
        },
        {
            "strategy": "RSI",
            "avg_oos_sharpe": 1.55,
            "avg_oos_win_rate": 0.59,
            "avg_oos_profit_factor": 1.62,
            "active_params": {"period": 14, "oversold": 30, "overbought": 70}
        },
        {
            "strategy": "MACD",
            "avg_oos_sharpe": 0.95,
            "avg_oos_win_rate": 0.51,
            "avg_oos_profit_factor": 1.22,
            "active_params": {"fast_period": 12, "slow_period": 26, "signal_period": 9}
        },
        {
            "strategy": "BollingerBands",
            "avg_oos_sharpe": 1.42,
            "avg_oos_win_rate": 0.57,
            "avg_oos_profit_factor": 1.55,
            "active_params": {"period": 20, "std_dev": 2.0}
        },
        {
            "strategy": "Breakout",
            "avg_oos_sharpe": 0.72,
            "avg_oos_win_rate": 0.46,
            "avg_oos_profit_factor": 1.12,
            "active_params": {"lookback_period": 20, "breakout_factor": 1.01}
        },
        {
            "strategy": "SupportResistance",
            "avg_oos_sharpe": 1.05,
            "avg_oos_win_rate": 0.53,
            "avg_oos_profit_factor": 1.28,
            "active_params": {"left_bars": 5, "right_bars": 5, "retest_threshold": 0.002}
        },
        {
            "strategy": "TrendPullback",
            "avg_oos_sharpe": 1.30,
            "avg_oos_win_rate": 0.56,
            "avg_oos_profit_factor": 1.48,
            "active_params": {"trend_period": 100, "pullback_rsi_period": 14, "pullback_rsi_trigger": 35}
        }
    ]


def compile_performance_report(history: list, output_filepath: str = None):
    """
    Consolidates the active run history and writes a cumulative metrics evaluation report.
    """
    if not history:
        return

    # Automatically resolve output report path via PathManager
    if output_filepath is None:
        output_filepath = PathManager.resolve_path("reports", "ai_performance_report.csv")

    file_exists = os.path.exists(output_filepath)
    fieldnames = [
        "timestamp", "symbol", "timeframe", "market_regime", 
        "selected_strategy", "confidence_score", "decision_action", "execution_ratio"
    ]

    # Calculate selection metrics
    total_runs = len(history)
    executes = sum(1 for h in history if h["decision_action"] == "EXECUTE")
    execution_ratio = round(executes / total_runs, 2) if total_runs > 0 else 0.0

    with open(output_filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in history:
            row_data = {
                "timestamp": record["timestamp"],
                "symbol": record["symbol"],
                "timeframe": record["timeframe"],
                "market_regime": record["market_regime"],
                "selected_strategy": record["selected_strategy"],
                "confidence_score": record["confidence_score"],
                "decision_action": record["decision_action"],
                "execution_ratio": execution_ratio
            }
            writer.writerow(row_data)

    print(f"[+] AI Performance Report generated successfully at: {output_filepath}")


def main():
    parser = argparse.ArgumentParser(
        description="Quantoryx AI Decision Engine (Phase 8 Standalone Test Suite)"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        default="EURUSD", 
        help="Target symbol ticker"
    )
    parser.add_argument(
        "--timeframe", 
        type=str, 
        default="1H", 
        help="Asset chart timeframe"
    )
    parser.add_argument(
        "--data", 
        type=str, 
        default=os.path.join("data", "EURUSD_1H.csv"), 
        help="Path to the historical CSV data file"
    )
    parser.add_argument(
        "--threshold", 
        type=float, 
        default=65.0, 
        help="Minimum confidence threshold to permit trade execution (0-100)"
    )

    args = parser.parse_args()

    # Initialize path infrastructure
    PathManager.initialize_workspace()

    # 1. Load Data
    print(f"[+] Loading dataset for context extraction: {args.data}")
    try:
        df = load_historical_data(args.data)
    except Exception as e:
        print(f"[-] Data Load error: {e}")
        return

    # 2. Extract current market regime
    print("[+] Running Market Regime analysis...")
    detector = MarketRegimeDetector()
    df_tagged = detector.classify_regimes(df)
    
    # Identify the current active regime
    active_regime = "Low Volatility"  # Fallback
    if not df_tagged.empty:
        active_regime = df_tagged['market_regime'].iloc[-1]
        if active_regime == "Unknown":
            # Search backward for the last known classification
            for i in range(len(df_tagged) - 1, -1, -1):
                if df_tagged['market_regime'].iloc[i] != "Unknown":
                    active_regime = df_tagged['market_regime'].iloc[i]
                    break

    print(f"[+] Active classified market regime at final bar: '{active_regime}'")

    # 3. Generate Mock Walk-Forward Summaries
    wfv_summaries = generate_mock_wfv_summaries()

    # 4. Instantiate and run the AI Decision Engine
    print("[+] Initializing AI Decision Engine...")
    ai_log_path = PathManager.resolve_path("logs", "ai_decision_log.csv")
    ai_engine = AIDecisionEngine(
        confidence_threshold=args.threshold,
        risk_level="Medium",
        log_filepath=ai_log_path
    )

    print("[+] Evaluating market context and walk-forward statistics...")
    decision = ai_engine.evaluate_current_state(
        symbol=args.symbol,
        timeframe=args.timeframe,
        current_regime=active_regime,
        wfv_summaries=wfv_summaries
    )

    # 5. Compile Performance Metrics
    perf_report_path = PathManager.resolve_path("reports", "ai_performance_report.csv")
    compile_performance_report(ai_engine.decisions_history, perf_report_path)

    # Console display output
    print("\n" + "=" * 70)
    print(" AI DECISION ENGINE RUN ANALYSIS SUMMARY")
    print("=" * 70)
    print(f" Active Regime:        '{decision['market_regime']}'")
    print(f" Strategy Nominated:   {decision['selected_strategy']}")
    print(f" Confidence Score:     {decision['confidence_score']:.1f} / 100")
    print(f" Decision Verdict:     {decision['decision_action']}")
    print("-" * 70)
    print(" Narrative Explanation:")
    # Pretty-print long text wraps
    text = decision['explanation']
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        if len(" ".join(current_line + [word])) > 66:
            lines.append(" ".join(current_line))
            current_line = [word]
        else:
            current_line.append(word)
    lines.append(" ".join(current_line))
    for line in lines:
        print(f"   {line}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
