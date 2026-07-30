# backend/api/endpoints.py
"""
Quantoryx — API Endpoints Router Module.

This module maps HTTP paths to backend operations, validating inputs through 
Pydantic model structures and delegating system computations to the QuantoryxService.
All sensitive simulation, analysis, data retrieval, and validator routes are protected
using secure dependency injection authentication gates.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from celery.result import AsyncResult

# Import auth dependencies
from backend.api.deps import get_current_user, get_current_admin_user, get_db

# Import schemas and services
from backend.schemas.api_schemas import (
    HealthResponse,
    VersionResponse,
    StatusResponse,
    BacktestRequest,
    BacktestResponse,
    OptimizeRequest,
    WalkForwardRequest,
    PaperTradingRequest,
    PaperTradingResponse,
    AIAnalysisRequest,
    AIAnalysisResponse,
    DashboardResponse,
    PortfolioResponse,
    ReportsListResponse,
    StrategiesResponse,
    MarketRegimeResponse,
    SystemHealthResponse
)
from backend.services.quantoryx_service import QuantoryxService
from backend.tasks.celery_app import celery_app
from backend.tasks.quant_tasks import run_optimization_task, run_walk_forward_task

# Initialize Router
router = APIRouter(prefix="/api", tags=["Quantoryx Core Engine API"])


# =====================================================================
# PUBLIC DIAGNOSTIC ENDPOINTS
# =====================================================================

@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Get API Operational Health",
    description="Returns operating uptime and UTC system times to monitor service integrity. (Public Endpoint)"
)
async def get_health():
    try:
        return QuantoryxService.get_health_status()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve system operational health: {str(e)}"
        )


@router.get(
    "/database-health",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Get Database Connection Health",
    description="Performs a live ping check against the database connection pool. (Public Endpoint)"
)
async def get_database_health():
    from backend.database.connection import check_db_health
    healthy, msg = check_db_health()
    if not healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=msg
        )
    return {"status": "HEALTHY", "message": msg}


@router.get(
    "/version",
    response_model=VersionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get System Version Metadata",
    description="Returns system branding details and semantic version codes. (Public Endpoint)"
)
async def get_version():
    try:
        return QuantoryxService.get_version_info()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve version specifications: {str(e)}"
        )


@router.get(
    "/status",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Framework Status Overview",
    description="Returns recognized instruments, chart timeframes, and folder initialization flags. (Public Endpoint)"
)
async def get_status():
    try:
        return QuantoryxService.get_system_status()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve framework statuses: {str(e)}"
        )


# =====================================================================
# PROTECTED SIMULATION & ANALYSIS ENDPOINTS (POST - User Access Required)
# =====================================================================

@router.post(
    "/backtest",
    response_model=BacktestResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Strategy Backtest",
    description="Runs a single-strategy backtest sweep over pricing history and compiles KPIs. (Auth Required)"
)
async def post_backtest(
    payload: BacktestRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        result = QuantoryxService.run_backtest_simulation(
            strategy=payload.strategy,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            fast_period=payload.fast_period,
            slow_period=payload.slow_period,
            custom_params=payload.custom_params
        )
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parameter verification failed: {str(ve)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest simulation sweep failed: {str(e)}"
        )


@router.post(
    "/optimize",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue Parameter Grid Optimization",
    description="Enqueues a parameter optimization task to run asynchronously in background workers [2]. Returns a Task UUID. (Auth Required)"
)
async def post_optimize(
    payload: OptimizeRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        # Deploy as background worker task (v5.0)
        task = run_optimization_task.delay(
            strategy=payload.strategy,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            metric=payload.metric,
            user_id=current_user["id"]
        )
        return {
            "task_id": task.id,
            "status": "QUEUED",
            "message": "Optimization sweep enqueued successfully."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue optimization task: {str(e)}"
        )


@router.post(
    "/walk-forward",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue Walk-Forward Validation",
    description="Enqueues a walk-forward validation sweep to run asynchronously in background workers [2]. Returns a Task UUID. (Auth Required)"
)
async def post_walk_forward(
    payload: WalkForwardRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        # Deploy as background worker task (v5.0)
        task = run_walk_forward_task.delay(
            strategy=payload.strategy,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            train_days=payload.train_days,
            test_days=payload.test_days,
            metric=payload.metric
        )
        return {
            "task_id": task.id,
            "status": "QUEUED",
            "message": "Walk-forward validation enqueued successfully."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue walk-forward task: {str(e)}"
        )


@router.post(
    "/paper-trading",
    response_model=PaperTradingResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Paper Trading Simulator",
    description="Executes virtual chronological orders on leveraged accounts, logging transactions and stops. (Auth Required)"
)
async def post_paper_trading(
    payload: PaperTradingRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        result = QuantoryxService.run_paper_trading_simulator(
            symbol=payload.symbol,
            capital=payload.capital,
            leverage=payload.leverage,
            spread=payload.spread,
            user_id=current_user["id"],
            db=db
        )
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Execution error: {str(ve)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Paper trading simulation run failed: {str(e)}"
        )


@router.post(
    "/ai-analysis",
    response_model=AIAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Run AI Decision Analysis",
    description="Evaluates indicator configurations, detects active regimes, and nominates champion models. (Auth Required)"
)
async def post_ai_analysis(
    payload: AIAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        result = QuantoryxService.run_ai_strategy_selection(
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            threshold=payload.threshold
        )
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AI context mapping failed: {str(ve)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI selection calculations failed: {str(e)}"
        )


# =====================================================================
# TASK TRACKING POLL ENPOINT (v5.0 Addition)
# =====================================================================

@router.get(
    "/tasks/{task_id}",
    status_code=status.HTTP_200_OK,
    summary="Get Asynchronous Task Status",
    description="Queries the Celery result backend for progress, state, and outputs of background tasks [2]. (Auth Required)"
)
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        # Query Celery state via AsyncResult (v5.0)
        async_result = AsyncResult(task_id, app=celery_app)
        
        response_data = {
            "task_id": task_id,
            "status": async_result.status,
            "result": None,
            "error": None
        }

        if async_result.status == "SUCCESS":
            response_data["result"] = async_result.result
        elif async_result.status == "FAILURE":
            response_data["error"] = str(async_result.result)
        elif async_result.status == "PROGRESS":
            response_data["result"] = async_result.info  # contains progress metadata dictionary

        return response_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query task status: {str(e)}"
        )


# =====================================================================
# PROTECTED DATA RETRIEVAL ENDPOINTS (GET - User Access Required)
# =====================================================================

@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Dashboard Summary Overview",
    description="Consolidates system states, active session indicators, and transaction summaries. (Auth Required)"
)
async def get_dashboard(current_user: dict = Depends(get_current_user)):
    try:
        return QuantoryxService.get_dashboard_summary_overview()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to consolidate dashboard information: {str(e)}"
        )


@router.get(
    "/portfolio",
    response_model=PortfolioResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Portfolio Equity Performance",
    description="Assembles floating balance curve datasets, peak drawdowns, and annualized Sharpe ratios. (Auth Required)"
)
async def get_portfolio(current_user: dict = Depends(get_current_user)):
    try:
        return QuantoryxService.get_portfolio_snapshot()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compile portfolio track snapshots: {str(e)}"
        )


@router.get(
    "/reports",
    response_model=ReportsListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Compiled System Reports",
    description="Scans standard output directories and lists registered CSV output documents. (Auth Required)"
)
async def get_reports(current_user: dict = Depends(get_current_user)):
    try:
        return QuantoryxService.get_reports_registry()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query system directories: {str(e)}"
        )


@router.get(
    "/strategies",
    response_model=StrategiesResponse,
    status_code=status.HTTP_200_OK,
    summary="List Registered Trading Strategies",
    description="Returns metadata specifications and default parameter definitions of strategies. (Auth Required)"
)
async def get_strategies(current_user: dict = Depends(get_current_user)):
    try:
        return QuantoryxService.get_strategies_metadata()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to inspect strategy registry: {str(e)}"
        )


@router.get(
    "/market-regime",
    response_model=MarketRegimeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Market Regime Distribution Statistics",
    description="Runs regime classification and aggregates indicators to yield distribution parameters. (Auth Required)"
)
async def get_market_regime(
    symbol: str = Query("EURUSD", description="Instrument symbol to query"),
    timeframe: str = Query("1H", description="Target timeframe interval"),
    current_user: dict = Depends(get_current_user)
):
    try:
        return QuantoryxService.get_market_regime_distribution(symbol, timeframe)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compile market regime distributions: {str(e)}"
        )


# =====================================================================
# CRITICAL DIAGNOSTIC CONTROL (GET - Admin Access Required Only)
# =====================================================================

@router.get(
    "/system-health",
    response_model=SystemHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Live System Health Diagnostics",
    description="Executes a system diagnostic pass checking imports, scanning AST codes, and validating output schemas. (Admin Only)"
)
async def get_system_health(current_user: dict = Depends(get_current_admin_user)):
    try:
        return QuantoryxService.run_system_health_validator()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run health validator suite: {str(e)}"
        )
