# backend/tasks/quant_tasks.py
"""
Quantoryx — Asynchronous Quantitative Research Task Definitions.

This module exposes background task wrappers for multi-parameter grid optimizations
and rolling walk-forward validation sweeps. Integrates with user database schemas
to persist completed analytical results [2].
"""

import os
import sys
from typing import Dict, Any, Optional

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.tasks.celery_app import celery_app
from backend.services.quantoryx_service import QuantoryxService
from backend.database.connection import SessionLocal
from backend.repositories.repositories import optimization_repo, audit_repo
from utils.logging_config import get_logger

logger = get_logger("backend.tasks.quant_tasks")


@celery_app.task(bind=True)
def run_optimization_task(
    self,
    strategy: str,
    symbol: str,
    timeframe: str,
    metric: str,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Asynchronously executes a grid parameter optimization sweep in a worker process [2].
    If a user_id is provided, commits the top ranked parameter combinations directly to
    the saved_optimizations database table.
    """
    logger.info("Task %s started: Optimizing %s (%s - %s)", self.request.id, strategy, symbol, timeframe)
    self.update_state(state="PROGRESS", meta={"status": "IN_PROGRESS", "progress": 25})

    try:
        # 1. Run the intensive optimization calculation
        results = QuantoryxService.run_optimization_sweep(
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
            metric=metric
        )
        self.update_state(state="PROGRESS", meta={"status": "COMPILING_RESULTS", "progress": 85})

        # 2. Optionally commit top results to RDBMS if associated with a user
        if user_id is not None:
            logger.info("Saving optimization results of Task %s to database for User %s", self.request.id, user_id)
            # SessionLocal() returns a plain Session, not a context manager.
            # Must use explicit try/finally to guarantee session closure.
            session = SessionLocal()
            try:
                optimization_data = {
                    "user_id": user_id,
                    "strategy_name": strategy,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "ranking_metric": metric,
                    "best_parameters": results["best_parameters"],
                    "total_combinations_tested": results["total_combinations_tested"],
                    "top_results": results["top_results"][:10]  # Persist top 10 ranked sets
                }

                db_opt = optimization_repo.create(session, obj_in=optimization_data)

                # Log event trace
                audit_repo.log_event(
                    session,
                    user_id=user_id,
                    action="ASYNC_OPTIMIZATION_COMPLETE",
                    entity_type="saved_optimizations",
                    entity_id=str(db_opt.id),
                    details=f"Asynchronous optimization task {self.request.id} completed and saved."
                )
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        logger.info("Task %s completed successfully.", self.request.id)
        return results

    except Exception as e:
        logger.error("Task %s failed with exception: %s", self.request.id, str(e), exc_info=True)
        self.update_state(state="FAILURE", meta={"status": "FAILED", "error": str(e)})
        raise e


@celery_app.task(bind=True)
def run_walk_forward_task(
    self,
    strategy: str,
    symbol: str,
    timeframe: str,
    train_days: int,
    test_days: int,
    metric: str
) -> Dict[str, Any]:
    """
    Asynchronously executes walk-forward rolling IS/OOS validation slices [2].
    Returns the fold summaries dictionary to the Celery backend storage.
    """
    logger.info("Task %s started: Walk-forward validation on %s (%s - %s)", self.request.id, strategy, symbol, timeframe)
    self.update_state(state="PROGRESS", meta={"status": "IN_PROGRESS", "progress": 30})

    try:
        results = QuantoryxService.run_walk_forward_validation(
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
            train_days=train_days,
            test_days=test_days,
            metric=metric
        )
        logger.info("Task %s completed successfully.", self.request.id)
        return results

    except Exception as e:
        logger.error("Task %s failed with exception: %s", self.request.id, str(e), exc_info=True)
        self.update_state(state="FAILURE", meta={"status": "FAILED", "error": str(e)})
        raise e
