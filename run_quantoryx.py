# run_quantoryx.py
"""Quantoryx unified master orchestrator (single-command pipeline).

Runs the full research pipeline end-to-end: regime detection →
walk-forward strategy selection → AI decision → risk gateways →
paper-trade simulation → consolidated report export.
"""

import argparse
import ast
import os
from typing import Any, Dict, List, Optional

import pandas as pd

# Core Configuration and Directory Managers
import config
from utils.logging_config import get_logger
from utils.path_manager import PathManager

logger = get_logger(__name__)


def _safe_parse_params(raw: Any) -> Dict[str, Any]:
    """Safely turn a stringified dict of parameters into a real dict.

    Uses :func:`ast.literal_eval` instead of :func:`eval` so untrusted
    strings can never execute arbitrary code.
    """
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = ast.literal_eval(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, SyntaxError):
        logger.warning("Could not parse parameters %r; defaulting to empty dict.", raw)
        return {}


def load_dataset_safely(file_path: str) -> Optional[pd.DataFrame]:
    """
    Safely loads and verifies the historical market data file.
    """
    if not os.path.exists(file_path):
        print(f"[-] Error: Historical dataset not found at {file_path}")
        return None
    try:
        df = pd.read_csv(file_path, parse_dates=True, index_col=0)
        df.sort_index(inplace=True)
        # Ensure mandatory columns are present
        required_cols = ["open", "high", "low", "close", "volume"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            print(f"[-] Error: Dataset is missing expected OHLCV columns: {missing}")
            return None
        return df
    except Exception as e:
        print(f"[-] Exception occurred while parsing dataset: {e}")
        return None


def run_autonomous_pipeline(
    symbol: str,
    timeframe: str,
    data_path: str,
    starting_capital: float,
    train_days: int,
    test_days: int,
    leverage: float,
    spread: float,
    confidence_threshold: float
):
    print("=" * 75)
    print(f" STARTING {config.SYSTEM_NAME.upper()} AUTONOMOUS QUANTITATIVE PIPELINE (v{config.VERSION})")
    print("=" * 75)

    # Initialize workspace folders safely
    PathManager.initialize_workspace()

    # --- Phase 1: Data Verification ---
    data_df = load_dataset_safely(data_path)
    if data_df is None or data_df.empty:
        print("[-] Pipeline Aborted: Missing or invalid historical price dataset.")
        return

    print(f"[+] Successfully verified dataset containing {len(data_df)} bars.")

    # --- Phase 2: Market Regime Classification ---
    print("\n[Phase 1/6] Running Market Regime Detection...")
    try:
        from market_regime.detector import MarketRegimeDetector
        detector = MarketRegimeDetector()
        data_tagged = detector.classify_regimes(data_df)
        
        regime_counts = data_tagged['market_regime'].value_counts()
        print("[+] Market Regime density map successfully compiled:")
        for regime, count in regime_counts.items():
            pct = (count / len(data_tagged)) * 100
            print(f"    - {regime:<20}: {count:>5} bars ({pct:.2f}%)")
    except Exception as e:
        print(f"[-] Critical Error in Market Regime Detection: {e}")
        return

    # --- Phase 3: Walk-Forward Multi-Strategy Selection ---
    print("\n[Phase 2/6] Initiating Walk-Forward Strategy Matrix...")
    candidate_strategies = ["EMA", "RSI", "MACD", "BollingerBands", "Breakout", "SupportResistance", "TrendPullback"]
    strategy_leaderboard = []
    all_wf_rows: List[Dict[str, Any]] = []  # accumulated fold results for the WFV report

    try:
        from walk_forward.validation_engine import WalkForwardValidator
    except ImportError as e:
        print(f"[-] Critical Import Error: {e}")
        return

    for strategy in candidate_strategies:
        print(f"    Evaluating Strategy Candidate: {strategy}...")
        try:
            validator = WalkForwardValidator(
                strategy_name=strategy,
                symbol=symbol,
                timeframe=timeframe,
                data_df=data_tagged,
                train_days=train_days,
                test_days=test_days,
                primary_metric="sharpe_ratio"
            )
            results = validator.run_validation()
            
            if results:
                # Tag each fold with its strategy and keep it for the WFV report.
                for r in results:
                    all_wf_rows.append({"strategy": strategy, **r})

                oos_sharpes = [r["oos_sharpe_ratio"] for r in results]
                oos_pnls = [r["oos_net_profit"] for r in results]
                oos_win_rates = [r["oos_win_rate"] for r in results]
                oos_profit_factors = [r["oos_profit_factor"] for r in results]
                
                avg_oos_sharpe = sum(oos_sharpes) / len(oos_sharpes)
                avg_oos_win_rate = sum(oos_win_rates) / len(oos_win_rates)
                avg_oos_profit_factor = sum(oos_profit_factors) / len(oos_profit_factors)
                total_oos_pnl = sum(oos_pnls)
                
                best_params = _safe_parse_params(results[-1]["parameters"])
                
                strategy_leaderboard.append({
                    "strategy": strategy,
                    "avg_oos_sharpe": avg_oos_sharpe,
                    "avg_oos_win_rate": avg_oos_win_rate,
                    "avg_oos_profit_factor": avg_oos_profit_factor,
                    "total_oos_pnl": total_oos_pnl,
                    "active_params": best_params
                })
        except Exception as e:
            print(f"    [-] Optimization skipped for {strategy} due to execution exception: {e}")

    if not strategy_leaderboard:
        print("[-] Pipeline Error: No strategies completed the Walk-Forward selection phase.")
        return

    # Persist the consolidated walk-forward report (consumed by the dashboard
    # and the validation suite).
    if all_wf_rows:
        wf_report_path = PathManager.resolve_path("reports", "walk_forward_report.csv")
        pd.DataFrame(all_wf_rows).to_csv(wf_report_path, index=False)
        print(f"[+] Walk-forward report written to: {wf_report_path}")

    # --- Phase 4: AI Decision Engine Analysis ---
    print(f"\n[Phase 3/6] Invoking {config.SYSTEM_NAME} Cognitive AI Decision Engine...")
    try:
        from ai_engine.decision_engine import AIDecisionEngine
        
        # Resolve target logging paths through PathManager
        ai_log_path = PathManager.resolve_path("logs", "ai_decision_log.csv")
        
        ai_decision_engine = AIDecisionEngine(
            confidence_threshold=confidence_threshold,
            risk_level="Medium",
            log_filepath=ai_log_path
        )

        wfv_summaries = []
        for item in strategy_leaderboard:
            wfv_summaries.append({
                "strategy": item["strategy"],
                "avg_oos_sharpe": item["avg_oos_sharpe"],
                "avg_oos_win_rate": item["avg_oos_win_rate"],
                "avg_oos_profit_factor": item["avg_oos_profit_factor"],
                "active_params": item["active_params"]
            })

        active_regime = "Low Volatility"
        if not data_tagged.empty:
            active_regime = data_tagged['market_regime'].iloc[-1]
            if active_regime == "Unknown":
                for i in range(len(data_tagged) - 1, -1, -1):
                    if data_tagged['market_regime'].iloc[i] != "Unknown":
                        active_regime = data_tagged['market_regime'].iloc[i]
                        break

        decision = ai_decision_engine.evaluate_current_state(
            symbol=symbol,
            timeframe=timeframe,
            current_regime=active_regime,
            wfv_summaries=wfv_summaries
        )

        best_strategy = decision["selected_strategy"]
        best_params = _safe_parse_params(decision["parameters"])
        confidence = decision["confidence_score"]
    except Exception as e:
        print(f"[-] Critical Error inside AI Decision Engine module: {e}")
        return

    print("\n" + "=" * 75)
    print(f" {config.SYSTEM_NAME.upper()} AI CHAMPION MODEL SELECTION NOMINATION")
    print("=" * 75)
    print(f" Nominated Model:     {best_strategy}")
    print(f" Confidence Rating:   {confidence:.1f} / 100")
    print(f" Action Verdict:      {decision['decision_action']}")
    print("=" * 75)

    if decision["decision_action"] == "SKIP":
        print("\n[-] AI Decision Engine issued a SKIP recommendation. Halting paper trading execution.")
        try:
            from run_ai_engine import compile_performance_report
            ai_perf_path = PathManager.resolve_path("reports", "ai_performance_report.csv")
            compile_performance_report(ai_decision_engine.decisions_history, ai_perf_path)
        except Exception as e:
            print(f"[-] Failed to write AI performance reports: {e}")
        return

    # --- Phase 5: Risk Validation & Position Sizing ---
    print("\n[Phase 4/6] Initializing Global Risk Gateways...")
    try:
        from risk.risk_manager import RiskManager
        from paper_trading.paper_engine import PaperTradingEngine
        
        # Load Risk parameters from config file
        r_limits = config.RISK_LIMITS
        risk_mgr = RiskManager(
            risk_per_trade_pct=r_limits["risk_per_trade_pct"],
            max_daily_loss_pct=r_limits["max_daily_loss_pct"],
            max_total_drawdown_pct=r_limits["max_total_drawdown_pct"],
            max_concurrent_trades=r_limits["max_concurrent_trades"],
            max_exposure_per_pair_pct=r_limits["max_exposure_per_pair_pct"],
            default_rr_ratio=r_limits["default_rr_ratio"]
        )
        
        paper_engine = PaperTradingEngine(
            starting_balance=starting_capital,
            leverage=leverage,
            spread_pct=spread,
            risk_manager=risk_mgr
        )
    except Exception as e:
        print(f"[-] Risk/Portfolio configuration initialization failed: {e}")
        return

    # --- Phase 6: Simulated Live Paper Trading Execution ---
    print(f"[Phase 5/6] Simulating transactions using strategy: {best_strategy}...")
    try:
        from engine.backtest_engine import BacktestEngine
        signal_helper = BacktestEngine(
            data=data_tagged,
            strategy_name=best_strategy,
            strategy_params=best_params
        )
        signals = signal_helper._generate_strategy_signals()

        for i in range(30, len(data_tagged)):
            timestamp = data_tagged.index[i]
            row = data_tagged.iloc[i]
            close_price = float(row['close'])
            regime = str(row['market_regime'])

            if i > 0 and hasattr(timestamp, 'date') and timestamp.date() != data_tagged.index[i-1].date():
                paper_engine.reset_daily_tracker()

            paper_engine.process_bar(timestamp, row, regime)

            sig = signals.iloc[i]
            if sig != 0:
                direction = "LONG" if sig == 1 else "SHORT"
                paper_engine.execute_order(
                    symbol=symbol,
                    direction=direction,
                    current_price=close_price,
                    stop_loss_pct=1.5,
                    rr_ratio=2.5,
                    timestamp=timestamp,
                    regime=regime
                )
    except Exception as e:
        print(f"[-] Error during simulated paper execution run: {e}")
        return

    # --- Phase 7: Consolidated Report Export ---
    print("\n[Phase 6/6] Compiling local database files and report indicators...")
    try:
        # Audit logs resolved cleanly
        paper_log_path = PathManager.resolve_path("trades", "paper_trade_log.csv")
        if paper_engine.trade_logs:
            pd.DataFrame(paper_engine.trade_logs).to_csv(paper_log_path, index=False)
            print(f"    [+] Saved trade logs successfully: {paper_log_path}")
            
            # Dynamic periodic report output resolved via PathManager
            from run_paper_trading import generate_periodic_reports
            perf_report_path = PathManager.resolve_path("reports", "paper_performance_report.csv")
            generate_periodic_reports(paper_engine.trade_logs, perf_report_path)
        else:
            print("    [-] Note: No trades executed during the Paper Trading simulation.")

        # Performance snapshot curve resolved via PathManager.
        # Emit the canonical [date, balance, equity, drawdown_pct] schema that
        # the dashboard and validation suite expect, deriving peak-to-trough
        # drawdown from the equity series.
        portfolio_report_path = PathManager.resolve_path("reports", "portfolio_report.csv")
        account_curve_df = pd.DataFrame(paper_engine.account_history)
        if not account_curve_df.empty:
            curve = account_curve_df.rename(columns={"timestamp": "date"}).copy()
            running_peak = curve["equity"].cummax()
            curve["drawdown_pct"] = ((running_peak - curve["equity"]) / running_peak * 100.0).round(4)
            portfolio_cols = ["date", "balance", "equity", "drawdown_pct"]
            curve[portfolio_cols].to_csv(portfolio_report_path, index=False)
            print(f"    [+] Saved portfolio curve snapshot history: {portfolio_report_path}")

        # AI performance tracking resolved via PathManager
        from run_ai_engine import compile_performance_report
        ai_perf_path = PathManager.resolve_path("reports", "ai_performance_report.csv")
        compile_performance_report(ai_decision_engine.decisions_history, ai_perf_path)
    except Exception as e:
        print(f"[-] Report compilation step raised an exception: {e}")

    # Quantoryx v2.0 Dashboard Console Metrics
    print("\n" + "=" * 75)
    print(f" {config.SYSTEM_NAME.upper()} AUTONOMOUS RUN SUCCESS SUMMARY REPORT (v{config.VERSION})")
    print("=" * 75)
    print(f" Asset Context:            {symbol} ({timeframe})")
    print(f" Champion Strategy:        {best_strategy}")
    print(f" Model Parameters:         {best_params}")
    print(f" Leverage Allocation:      1:{leverage:.0f}")
    print(f" Spread Cost Applied:      {spread * 100:.4f}%")
    print("-" * 75)
    print(f" Initial Fund Allocation:  {starting_capital:,.2f}")
    print(f" Ending Equity Value:      {paper_engine.equity:,.2f}")
    print(f" Total Realized Trades:    {len(paper_engine.trade_logs)}")
    print(f" Active Inventory:         {len(paper_engine.active_positions)}")
    print(f" Maximum Peak Drawdown:    {paper_engine.risk_manager.account_drawdown_pct * 100:.2f}%")
    print("=" * 75 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description=f"{config.SYSTEM_NAME} Autonomous Algorithmic Engine (v{config.VERSION} Core Orchestrator)"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        default="EURUSD", 
        help="Target trading asset (default: EURUSD)"
    )
    parser.add_argument(
        "--timeframe", 
        type=str, 
        default="1H", 
        help="Target dataset timeframe (default: 1H)"
    )
    parser.add_argument(
        "--data", 
        type=str, 
        default=os.path.join("data", "EURUSD_1H.csv"), 
        help="Path to historical price data (default: data/EURUSD_1H.csv)"
    )
    parser.add_argument(
        "--capital", 
        type=float, 
        default=config.DEFAULT_CAPITAL, 
        help=f"Simulated base trading capital (default: {config.DEFAULT_CAPITAL})"
    )
    parser.add_argument(
        "--train-days", 
        type=int, 
        default=180, 
        help="Length of In-Sample window in calendar days (default: 180)"
    )
    parser.add_argument(
        "--test-days", 
        type=int, 
        default=60, 
        help="Length of Out-of-Sample window in calendar days (default: 60)"
    )
    parser.add_argument(
        "--leverage", 
        type=float, 
        default=config.DEFAULT_LEVERAGE, 
        help=f"Account leverage multiplier (default: {config.DEFAULT_LEVERAGE})"
    )
    parser.add_argument(
        "--spread", 
        type=float, 
        default=config.DEFAULT_SPREAD, 
        help=f"Assumed standard transaction spread cost (default: {config.DEFAULT_SPREAD})"
    )
    parser.add_argument(
        "--threshold", 
        type=float, 
        default=config.DEFAULT_CONFIDENCE_THRESHOLD, 
        help=f"Minimum confidence threshold required by the AI Engine to trade (default: {config.DEFAULT_CONFIDENCE_THRESHOLD})"
    )

    args = parser.parse_args()

    # Automatically generate dataset if missing so the system runs immediately out-of-the-box
    if not os.path.exists(args.data):
        print(f"[-] Historical data file not detected at: {args.data}")
        print("[+] Creating a synthetic pricing dataset automatically...")
        try:
            from utils.generate_mock_data import generate_synthetic_ohlcv
            os.makedirs(os.path.dirname(args.data), exist_ok=True)
            # ~1 year of 1H data — enough for the default 180/60-day windows.
            mock_df = generate_synthetic_ohlcv(symbol=args.symbol, timeframe=args.timeframe, bars=9000)
            mock_df.to_csv(args.data)
            print(f"[+] Synthetic data written to: {args.data}")
        except Exception as e:
            print(f"[-] Automated dataset creation failed: {e}")
            return

    # Trigger core pipeline execution
    run_autonomous_pipeline(
        symbol=args.symbol,
        timeframe=args.timeframe,
        data_path=args.data,
        starting_capital=args.capital,
        train_days=args.train_days,
        test_days=args.test_days,
        leverage=args.leverage,
        spread=args.spread,
        confidence_threshold=args.threshold
    )


if __name__ == "__main__":
    main()
