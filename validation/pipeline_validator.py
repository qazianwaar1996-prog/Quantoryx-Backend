# validation/pipeline_validator.py

import os
import sys
import ast
import time
import json
import importlib
import tracemalloc
from typing import Dict, List, Any, Tuple

from utils.path_manager import PathManager


class PipelineValidator:
    """
    Automated system validation and profiling tool.
    Analyzes code structures, benchmarks runtime performance, 
    verifies file logs, and compiles a comprehensive system health report.
    """
    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir
        self.health_checks: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "PASS",
            "modules_validation": {},
            "static_code_analysis": {},
            "report_audit": {},
            "benchmarks": {},
            "warnings": [],
            "recommendations": []
        }
        self.validation_logs: List[Dict[str, Any]] = []

    def log_event(self, category: str, item: str, status: str, message: str):
        """
        Logs validation steps for auditing.
        """
        self.validation_logs.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": category,
            "item": item,
            "status": status,
            "message": message
        })

    def validate_module_integrations(self) -> bool:
        """
        Verifies that every core Quantoryx module can be successfully imported 
        and has basic compatibility.
        """
        target_modules = [
            ("engine.backtest_engine", "BacktestEngine"),
            ("optimizer.param_ranges", "generate_combinations"),
            ("optimizer.optimizer_engine", "OptimizerEngine"),
            ("market_regime.detector", "MarketRegimeDetector"),
            ("market_regime.analyzer", "MarketRegimeAnalyzer"),
            ("walk_forward.validation_engine", "WalkForwardValidator"),
            ("risk.risk_manager", "RiskManager"),
            ("portfolio.portfolio_manager", "PortfolioManager"),
            ("paper_trading.paper_engine", "PaperTradingEngine"),
            ("ai_engine.decision_engine", "AIDecisionEngine"),
            
            # v4.5, v5.0, v6.0 Core Backend Integrations (Added in audit updates)
            ("backend.services.portfolio_services", "PortfolioService"),
            ("backend.api.portfolio_endpoints", "router"),
            ("backend.api.ws_endpoints", "router"),
            ("backend.tasks.celery_app", "celery_app"),
            ("backend.tasks.quant_tasks", "run_optimization_task")
        ]

        all_passed = True
        print("[+] Commencing Quantoryx module integration validation...")

        for module_path, class_name in target_modules:
            try:
                module = importlib.import_module(module_path)
                component = getattr(module, class_name, None)
                if component is None:
                    raise AttributeError(f"Component '{class_name}' missing in module '{module_path}'.")
                
                self.health_checks["modules_validation"][module_path] = "OK"
                self.log_event("INTEGRATION", module_path, "SUCCESS", f"Imported '{class_name}' successfully.")
            except Exception as e:
                all_passed = False
                self.health_checks["modules_validation"][module_path] = "FAIL"
                self.health_checks["warnings"].append(f"Module '{module_path}' load failure: {e}")
                self.log_event("INTEGRATION", module_path, "FAILED", str(e))
                print(f"    [-] Integration failure: {module_path} -> {e}")

        return all_passed

    def static_code_analysis(self):
        """
        Parses all Python source files using AST to identify unused imports
        and scans for duplicate code blocks.
        """
        print("[+] Conducting static code analysis (AST parsing)...")
        py_files = self._get_all_python_files()
        
        unused_imports = {}
        all_lines_map: Dict[str, List[Tuple[str, int]]] = {}  # Normalized line text -> List of (filepath, line_no)
        duplicate_blocks = []

        for filepath in py_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # 1. AST Check for Unused Imports
                tree = ast.parse(content, filename=filepath)
                imported_names = {}
                used_names = set()

                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        for alias in node.names:
                            imported_names[alias.name] = alias.asname or alias.name
                    elif isinstance(node, ast.Name):
                        if isinstance(node.ctx, ast.Load):
                            used_names.add(node.id)

                file_unused = [name for name, bound in imported_names.items() if bound not in used_names]
                if file_unused:
                    unused_imports[filepath] = file_unused

                # 2. Store lines for duplicate block matching
                lines = content.splitlines()
                for i, raw_line in enumerate(lines, 1):
                    normalized = "".join(raw_line.split()) # strip whitespace
                    if len(normalized) > 15:  # filter out short lines, brackets, comments
                        all_lines_map.setdefault(normalized, []).append((filepath, i))
                        
            except Exception as e:
                self.health_checks["warnings"].append(f"Static analysis skipped for {filepath}: {e}")

        # Basic duplicate checker (identifying matching normalized lines across different files)
        duplicates_count = 0
        for norm_line, matches in all_lines_map.items():
            if len(matches) > 1:
                files_involved = list(set([m[0] for m in matches]))
                if len(files_involved) > 1:
                    duplicates_count += 1
                    if duplicates_count <= 5:  # Cap logging to avoid file bloat
                        duplicate_blocks.append({
                            "line_sample": norm_line[:50],
                            "locations": [f"{m[0]}:{m[1]}" for m in matches]
                        })

        # Record findings
        self.health_checks["static_code_analysis"] = {
            "scanned_files_count": len(py_files),
            "unused_imports": unused_imports,
            "duplicate_line_matches_count": duplicates_count
        }

        # Recommendations based on static results
        if unused_imports:
            self.health_checks["recommendations"].append("Remove flagged unused imports to reduce memory overhead and speed up runtime loading.")
        if duplicates_count > 50:
            self.health_checks["recommendations"].append("Refactor duplicate code blocks into shared utilities inside the 'utils/' module.")

    def audit_performance_reports(self):
        """
        Validates the presence, file sizes, and schema structure of all generated reports.
        """
        print("[+] Commencing audit of system reports and database logs...")
        # (category, filename): expected header schema. Locations are resolved
        # through PathManager so the audit matches where the pipeline writes.
        required_reports = {
            ("reports", "portfolio_report.csv"): ["date", "balance", "equity", "drawdown_pct"],
            ("trades", "paper_trade_log.csv"): ["symbol", "direction", "entry_time", "exit_time", "pnl"],
            ("logs", "ai_decision_log.csv"): ["timestamp", "symbol", "selected_strategy", "confidence_score"],
            ("reports", "ai_performance_report.csv"): ["timestamp", "symbol", "selected_strategy", "decision_action"],
            ("reports", "walk_forward_report.csv"): ["fold", "train_start", "is_sharpe_ratio", "oos_sharpe_ratio"],
        }

        audit_results = {}

        for (category, filename), expected_headers in required_reports.items():
            # Prefer the canonical PathManager location; fall back to root for
            # backward compatibility with older sessions.
            filepath = PathManager.resolve_path(category, filename)
            if not os.path.exists(filepath):
                legacy = os.path.join(self.root_dir, filename)
                if os.path.exists(legacy):
                    filepath = legacy
            if not os.path.exists(filepath):
                audit_results[filename] = "MISSING"
                self.health_checks["warnings"].append(f"Expected system output '{filename}' is missing.")
                self.log_event("REPORT_AUDIT", filename, "FAIL", "File is missing.")
                continue

            # Check size
            size_kb = os.path.getsize(filepath) / 1024.0
            if size_kb == 0:
                audit_results[filename] = "EMPTY_FILE"
                self.health_checks["warnings"].append(f"System output '{filename}' exists but is empty (0 bytes).")
                self.log_event("REPORT_AUDIT", filename, "WARNING", "File exists but has no data.")
                continue

            # Check header schema
            try:
                df_temp = pd_read_header(filepath)
                headers = list(df_temp.columns)
                missing_cols = [col for col in expected_headers if col not in headers]
                if missing_cols:
                    audit_results[filename] = f"SCHEMA_MISMATCH: Missing columns {missing_cols}"
                    self.health_checks["warnings"].append(f"Schema mismatch detected in '{filename}'. Missing columns: {missing_cols}")
                else:
                    audit_results[filename] = f"OK ({size_kb:.2f} KB)"
                    self.log_event("REPORT_AUDIT", filename, "SUCCESS", f"Schema verified. Size: {size_kb:.2f} KB")
            except Exception as e:
                audit_results[filename] = f"READ_ERROR: {e}"
                self.log_event("REPORT_AUDIT", filename, "FAIL", str(e))

        self.health_checks["report_audit"] = audit_results

    def profile_benchmark_run(self, pipeline_run_callback) -> Dict[str, Any]:
        """
        Profiles the processing execution speed and monitors peak memory usage.
        """
        print("[+] Commencing runtime performance profiling...")
        
        # Start tracking memory
        tracemalloc.start()
        start_time = time.perf_counter()

        try:
            # Execute pipeline callback
            pipeline_run_callback()
            success = True
            error_msg = ""
        except Exception as e:
            success = False
            error_msg = str(e)
            self.health_checks["warnings"].append(f"Runtime execution benchmark failed: {e}")

        # Stop tracking memory
        elapsed_time = time.perf_counter() - start_time
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024.0 * 1024.0)

        benchmark_data = {
            "execution_status": "SUCCESS" if success else f"FAIL: {error_msg}",
            "execution_time_seconds": round(elapsed_time, 3),
            "peak_memory_usage_mb": round(peak_mb, 2)
        }

        self.health_checks["benchmarks"] = benchmark_data

        # Assess performance budgets. 60s is a realistic ceiling for a full
        # 7-strategy walk-forward benchmark on the synthetic validation set.
        if elapsed_time > 60.0:
            self.health_checks["warnings"].append(f"Performance limit reached. Pipeline run took {elapsed_time:.2f} seconds.")
            self.health_checks["recommendations"].append("Consider enabling parameter constraints or pre-calculating regimes to optimize runtime.")
        if peak_mb > 150.0:
            self.health_checks["warnings"].append(f"Memory threshold warning: peak usage exceeded 150 MB ({peak_mb:.1f} MB).")

        return benchmark_data

    def compile_health_report(self, output_path: str = "system_health_report.json"):
        """
        Consolidates the active check matrices and outputs the JSON system health report.
        """
        if self.health_checks["warnings"]:
            self.health_checks["status"] = "WARNING"
            
        for mod, stat in self.health_checks["modules_validation"].items():
            if stat == "FAIL":
                self.health_checks["status"] = "CRITICAL"
                break

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.health_checks, f, indent=4)

        print(f"[+] System Health Report saved successfully to: {output_path}")

    def _get_all_python_files(self) -> List[str]:
        """
        Utility to fetch all local Python source files in the framework.
        """
        py_files = []
        for root, dirs, files in os.walk(self.root_dir):
            if any(part.startswith(".") or part in ["env", "venv", "build"] for part in root.split(os.sep)):
                continue
            for file in files:
                # Exclude validation helper and master orchestrator runs to prevent recursive scans
                if file.endswith(".py") and file not in ["run_validation.py", "run_quantoryx.py"]:
                    py_files.append(os.path.join(root, file))
        return py_files


def pd_read_header(filepath: str) -> Any:
    import pandas as pd
    return pd.read_csv(filepath, nrows=0)
