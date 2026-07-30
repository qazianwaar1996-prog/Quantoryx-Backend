# run_validation.py

import os
import csv
import argparse
import pandas as pd
from validation.pipeline_validator import PipelineValidator


def export_validation_logs(logs: list, filepath: str = "validation_log.csv"):
    """
    Exports chronological step results of the validation run to a CSV file.
    """
    if not logs:
        return

    fieldnames = ["timestamp", "category", "item", "status", "message"]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(logs)

    print(f"[+] Validation logs exported successfully to: {filepath}")


def run_benchmark_callback(symbol: str, timeframe: str, data_path: str):
    """
    A lightweight wrapper that executes the full autonomous pipeline 
    as an end-to-end validation callback.
    """
    from run_quantoryx import run_autonomous_pipeline
    
    # We run a shortened window to keep benchmark footprint fast and light
    run_autonomous_pipeline(
        symbol=symbol,
        timeframe=timeframe,
        data_path=data_path,
        starting_capital=100000.0,
        train_days=60,   # Shorter windows for quick validation
        test_days=20,    # Shorter windows for quick validation
        leverage=30.0,
        spread=0.0002,
        confidence_threshold=65.0
    )


def main():
    parser = argparse.ArgumentParser(
        description="Quantoryx Automated System Validation Suite"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        default="EURUSD", 
        help="Target validation asset (default: EURUSD)"
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
        # Dedicated, right-sized dataset so the end-to-end benchmark stays fast
        # and never collides with a large production data/EURUSD_1H.csv file.
        default="data/validation_EURUSD_1H.csv",
        help="Path to validation data file (default: data/validation_EURUSD_1H.csv)"
    )

    args = parser.parse_args()

    # Automatically generate dataset if missing so validator can execute
    if not os.path.exists(args.data):
        print(f"[-] Historical data file not detected at: {args.data}")
        print("[+] Creating a synthetic validation dataset automatically...")
        try:
            from utils.generate_mock_data import generate_synthetic_ohlcv
            os.makedirs(os.path.dirname(args.data), exist_ok=True)
            # ~125 days of 1H data → a handful of 60/20-day folds: enough to
            # exercise the whole pipeline while keeping the benchmark quick.
            mock_df = generate_synthetic_ohlcv(symbol=args.symbol, timeframe=args.timeframe, bars=3000)
            mock_df.to_csv(args.data)
            print(f"[+] Synthetic validation data written to: {args.data}")
        except Exception as e:
            print(f"[-] Automated dataset creation failed: {e}")
            return

    # 1. Initialize Validator
    validator = PipelineValidator(root_dir=".")

    # 2. Run Module Integration Verification
    modules_ok = validator.validate_module_integrations()

    # 3. Run Static Code Quality Check (AST)
    validator.static_code_analysis()

    # 4. Profile and Benchmark the entire End-to-End Pipeline
    print("[+] Commencing live end-to-end benchmark profiling (may take several seconds)...")
    
    # Use a lambda callback to feed our pipeline execution runner
    benchmark_callback = lambda: run_benchmark_callback(
        symbol=args.symbol,
        timeframe=args.timeframe,
        data_path=args.data
    )
    
    benchmark_data = validator.profile_benchmark_run(benchmark_callback)

    # 5. Audit output logs and performance reports
    validator.audit_performance_reports()

    # 6. Save final reports
    validator.compile_health_report(output_path="system_health_report.json")
    export_validation_logs(validator.validation_logs, "validation_log.csv")

    # 7. Print Terminal Health Summary
    health = validator.health_checks
    status_colors = {
        "PASS": "\033[92mPASS\033[0m",
        "WARNING": "\033[93mWARNING\033[0m",
        "CRITICAL": "\033[91mCRITICAL\033[0m"
    }
    colored_status = status_colors.get(health["status"], health["status"])

    print("\n" + "=" * 70)
    print(" SYSTEM HEALTH AUDIT SUMMARY (QUANTORYX v2.0)")
    print("=" * 70)
    print(f" Overall Status:       {colored_status}")
    print(f" Audited Modules:      {len(health['modules_validation'])} checked")
    print(f" Benchmark Run Time:   {benchmark_data.get('execution_time_seconds', 0.0):.2f} seconds")
    print(f" Peak Memory Usage:    {benchmark_data.get('peak_memory_usage_mb', 0.0):.2f} MB")
    print(f" Total Warnings Logged: {len(health['warnings'])}")
    print("-" * 70)
    
    if health["warnings"]:
        print(" Active Warnings:")
        for warn in health["warnings"][:5]:  # show top 5
            print(f"   [!] {warn}")
        if len(health["warnings"]) > 5:
            print(f"   ... and {len(health['warnings']) - 5} other warnings (see system_health_report.json)")
            
    if health["recommendations"]:
        print("\n Recommended Actions:")
        for rec in health["recommendations"]:
            print(f"   [*] {rec}")
            
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
