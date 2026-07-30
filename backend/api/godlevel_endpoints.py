# backend/api/godlevel_endpoints.py
"""
Quantoryx God-Level API — Master Router.

Exposes ALL new platform systems via clean REST endpoints:
  /api/gl/strategies/*       — 18 strategies + registry
  /api/gl/consensus          — Signal Consensus Engine
  /api/gl/prop/*             — Prop Firm Challenge Mode
  /api/gl/evolve             — Genetic Algorithm Optimizer
  /api/gl/blackswan/*        — Black Swan Defense System
  /api/gl/marketplace/*      — Strategy Marketplace
  /api/gl/mirror/*           — Multi-Account Signal Mirror
  /api/gl/mql               — MQL4/MQL5 Code Generator
  /api/gl/correlation        — Real-Time Correlation Scanner
  /api/gl/coach              — AI Performance Coach
  /api/gl/risk-rating        — Strategy Risk Rating
  /api/gl/tiers              — Subscription Tier System
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.api.deps import get_current_user
from utils.logging_config import get_logger

logger = get_logger("backend.api.godlevel")
router = APIRouter(prefix="/api/gl", tags=["God-Level Platform"])


# ─── Shared Schemas ────────────────────────────────────────────────────────────

class CandleIn(BaseModel):
    time: str; open: float; high: float; low: float; close: float; volume: float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGY REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/strategies", summary="Get full strategy catalog")
async def strategy_catalog():
    from strategies import get_strategy_metadata, CATEGORIES, REGIME_FIT
    return {"strategies": get_strategy_metadata(), "categories": CATEGORIES, "regime_fit": REGIME_FIT, "total": 18}


@router.get("/strategies/for-regime/{regime}", summary="Strategies best for a regime")
async def strategies_for_regime(regime: str):
    from strategies import strategies_for_regime
    return {"regime": regime, "recommended": strategies_for_regime(regime)}


@router.post("/strategies/{name}/run", summary="Run a strategy on OHLCV data")
async def run_strategy(name: str, body: Dict = None, user=Depends(get_current_user)):
    try:
        import pandas as pd
        from strategies import get_strategy
        if not body or "candles" not in body:
            raise HTTPException(400, "Provide 'candles' array.")
        df = pd.DataFrame(body["candles"])
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"]); df = df.set_index("time")
        strategy = get_strategy(name, body.get("params"))
        result = strategy.run(df)
        signals = result["signal"].tolist()
        last = int(signals[-1]) if signals else 0
        return {
            "strategy": name, "last_signal": last,
            "signal_label": {1:"BUY",-1:"SELL",0:"HOLD"}.get(last,"HOLD"),
            "signal_count": sum(1 for s in signals if s != 0),
            "signals": signals[-50:],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# CONSENSUS ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class ConsensusReq(BaseModel):
    symbol: str = "EURUSD"
    candles: List[CandleIn]
    strategy_names: Optional[List[str]] = None
    consensus_threshold: float = 0.55
    min_votes: int = 3
    weights: Optional[Dict[str, float]] = None

@router.post("/consensus", summary="Multi-strategy consensus signal")
async def consensus(req: ConsensusReq, user=Depends(get_current_user)):
    try:
        import pandas as pd
        from signals.consensus_engine import SignalConsensusEngine
        if len(req.candles) < 50:
            raise HTTPException(400, "Minimum 50 candles required.")
        df = pd.DataFrame([c.model_dump() for c in req.candles])
        df["time"] = pd.to_datetime(df["time"]); df = df.set_index("time")
        engine = SignalConsensusEngine(req.strategy_names, req.weights or {}, req.consensus_threshold, req.min_votes)
        r = engine.evaluate(df)
        return {"symbol": req.symbol, "signal": {1:"BUY",-1:"SELL",0:"HOLD"}.get(r.signal,"HOLD"),
                "confidence": r.confidence, "votes_buy": r.votes_buy, "votes_sell": r.votes_sell,
                "votes_hold": r.votes_hold, "breakdown": r.strategy_votes, "regime": r.regime}
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# PROP FIRM CHALLENGE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/prop/presets", summary="List all prop firm presets")
async def prop_presets():
    from prop_firm.challenge_engine import PropFirmChallengeEngine
    return PropFirmChallengeEngine().get_available_presets()

class PropSimReq(BaseModel):
    preset: str = "ftmo_standard"
    trades: List[float]
    dates: Optional[List[str]] = None

@router.post("/prop/simulate", summary="Simulate a prop firm challenge")
async def prop_simulate(req: PropSimReq, user=Depends(get_current_user)):
    try:
        from prop_firm.challenge_engine import PropFirmChallengeEngine
        engine = PropFirmChallengeEngine(req.preset)
        return engine.simulate_backtest(req.trades, req.dates)
    except Exception as e:
        raise HTTPException(500, str(e))

class PropTradeReq(BaseModel):
    preset: str = "ftmo_standard"
    pnl: float
    date: Optional[str] = None

_prop_sessions: Dict[str, Any] = {}

@router.post("/prop/start/{user_id}", summary="Start a live challenge session")
async def prop_start(user_id: str, preset: str = "ftmo_standard", user=Depends(get_current_user)):
    from prop_firm.challenge_engine import PropFirmChallengeEngine
    engine = PropFirmChallengeEngine(preset)
    engine.start_challenge()
    _prop_sessions[user_id] = engine
    return engine.get_status()

@router.post("/prop/trade/{user_id}", summary="Record a trade in active challenge")
async def prop_trade(user_id: str, req: PropTradeReq, user=Depends(get_current_user)):
    engine = _prop_sessions.get(user_id)
    if not engine:
        raise HTTPException(404, "No active challenge. POST /prop/start/{user_id} first.")
    return engine.record_trade(req.pnl, req.date)

@router.get("/prop/status/{user_id}", summary="Get active challenge status")
async def prop_status(user_id: str, user=Depends(get_current_user)):
    engine = _prop_sessions.get(user_id)
    if not engine:
        raise HTTPException(404, "No active challenge.")
    return engine.get_status()


# ══════════════════════════════════════════════════════════════════════════════
# GENETIC ALGORITHM OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════

class EvolveReq(BaseModel):
    strategy_name: str
    candles: List[CandleIn]
    population_size: int = Field(30, ge=10, le=100)
    generations: int = Field(20, ge=5, le=50)
    mutation_rate: float = 0.20

@router.post("/evolve", summary="Genetic algorithm strategy optimization")
async def evolve_strategy(req: EvolveReq, user=Depends(get_current_user)):
    try:
        import pandas as pd
        from evolution.genetic_optimizer import GeneticStrategyOptimizer
        df = pd.DataFrame([c.model_dump() for c in req.candles])
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"]); df = df.set_index("time")
        opt = GeneticStrategyOptimizer(
            strategy_name=req.strategy_name, df=df,
            population_size=req.population_size, generations=req.generations,
            mutation_rate=req.mutation_rate,
        )
        result = opt.evolve()
        return {
            "strategy": req.strategy_name,
            "best_params": result.best_params,
            "best_fitness_sharpe": result.best_fitness,
            "best_generation": result.best_generation,
            "improvement_pct": result.improvement_pct,
            "total_backtests": result.total_backtests_run,
            "fitness_history": result.fitness_history,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# BLACK SWAN DEFENSE
# ══════════════════════════════════════════════════════════════════════════════

class BlackSwanReq(BaseModel):
    pair_candles: Dict[str, List[CandleIn]]   # {pair: [candles]}
    spreads: Optional[Dict[str, float]] = None

@router.post("/blackswan/evaluate", summary="Black Swan market health evaluation")
async def blackswan_evaluate(req: BlackSwanReq, user=Depends(get_current_user)):
    try:
        import pandas as pd
        from black_swan.defense_system import BlackSwanDefenseSystem
        defense = BlackSwanDefenseSystem()
        dfs = []
        for pair, candles in req.pair_candles.items():
            df = pd.DataFrame([c.model_dump() for c in candles])
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"]); df = df.set_index("time")
            dfs.append(df)
        snap = defense.evaluate(*dfs, spreads=req.spreads)
        return {
            "timestamp": snap.timestamp,
            "threat_level": snap.threat_level.level,
            "threat_label": snap.threat_level.label,
            "threat_color": snap.threat_level.color,
            "recommended_action": snap.threat_level.recommended_action,
            "vol_ratio": snap.vol_ratio,
            "flash_crash": snap.flash_crash_detected,
            "correlation_spike": snap.correlation_spike,
            "active_alerts": snap.active_alerts,
            "is_locked_down": snap.is_locked_down,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGY MARKETPLACE
# ══════════════════════════════════════════════════════════════════════════════

_marketplace = None
def _get_marketplace():
    global _marketplace
    if _marketplace is None:
        from marketplace.strategy_marketplace import StrategyMarketplace
        _marketplace = StrategyMarketplace()
    return _marketplace

@router.get("/marketplace", summary="Browse strategy marketplace")
async def browse_marketplace(sort_by: str = "trending", free_only: bool = False, search: str = None):
    return {"listings": _get_marketplace().get_listings(sort_by=sort_by, free_only=free_only, search=search)}

class PublishReq(BaseModel):
    display_name: str; strategy_type: str; description: str
    pairs: List[str]; timeframe: str; backtest_results: Dict
    price_usd_monthly: float = 0.0; tags: List[str] = []

@router.post("/marketplace/publish", summary="Publish strategy to marketplace")
async def publish_strategy(req: PublishReq, user=Depends(get_current_user)):
    listing = _get_marketplace().publish_strategy(
        creator_id=user.get("id","anon"), display_name=req.display_name,
        strategy_type=req.strategy_type, description=req.description,
        pairs=req.pairs, timeframe=req.timeframe, backtest_results=req.backtest_results,
        price_usd_monthly=req.price_usd_monthly, tags=req.tags,
    )
    return {"published": True, "listing_id": listing.listing_id}

@router.post("/marketplace/{listing_id}/subscribe", summary="Subscribe to a strategy")
async def subscribe(listing_id: str, user=Depends(get_current_user)):
    return _get_marketplace().subscribe(user.get("id","anon"), listing_id)

@router.get("/marketplace/earnings", summary="Creator earnings dashboard")
async def creator_earnings(user=Depends(get_current_user)):
    return _get_marketplace().get_creator_earnings(user.get("id","anon"))


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL MIRROR
# ══════════════════════════════════════════════════════════════════════════════

_mirrors: Dict[str, Any] = {}
def _get_mirror(master_id: str):
    if master_id not in _mirrors:
        from mirror.signal_mirror import SignalMirrorEngine
        _mirrors[master_id] = SignalMirrorEngine(master_id)
    return _mirrors[master_id]

class SlaveReq(BaseModel):
    slave_id: str; name: str; broker: str = "paper"; account_number: str = "demo"
    lot_multiplier: float = 1.0; allowed_pairs: List[str] = []; allowed_strategies: List[str] = []
    is_reversed: bool = False; delay_seconds: int = 0; max_lot_size: float = 10.0

@router.post("/mirror/{master_id}/add-slave", summary="Add slave account to mirror")
async def add_slave(master_id: str, req: SlaveReq, user=Depends(get_current_user)):
    from mirror.signal_mirror import SlaveAccount
    slave = SlaveAccount(**req.model_dump())
    return _get_mirror(master_id).add_slave(slave)

@router.get("/mirror/{master_id}/slaves", summary="List all slave accounts")
async def list_slaves(master_id: str, user=Depends(get_current_user)):
    return {"slaves": _get_mirror(master_id).list_slaves()}

@router.get("/mirror/{master_id}/log", summary="Signal mirror copy log")
async def mirror_log(master_id: str, user=Depends(get_current_user)):
    return {"log": _get_mirror(master_id).get_mirror_log(), "stats": _get_mirror(master_id).get_mirror_stats()}


# ══════════════════════════════════════════════════════════════════════════════
# MQL CODE GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

class MQLReq(BaseModel):
    strategy_name: str; params: Dict = {}
    risk_pct: float = 1.0; version: int = 4
    pair: str = "EURUSD"; timeframe: str = "H1"

@router.post("/mql/generate", summary="Generate MQL4/MQL5 Expert Advisor code")
async def generate_mql(req: MQLReq, user=Depends(get_current_user)):
    from mql_generator.code_generator import MQLCodeGenerator
    return MQLCodeGenerator().generate(
        req.strategy_name, req.params, req.risk_pct, req.version, req.pair, req.timeframe
    )


# ══════════════════════════════════════════════════════════════════════════════
# CORRELATION SCANNER
# ══════════════════════════════════════════════════════════════════════════════

class CorrReq(BaseModel):
    price_data: Dict[str, List[float]]   # {pair: [prices]}
    lookback: int = 20
    open_pairs: Optional[List[str]] = None

@router.post("/correlation/scan", summary="Real-time correlation scan across pairs")
async def correlation_scan(req: CorrReq, user=Depends(get_current_user)):
    try:
        import pandas as pd
        from correlation_scanner.scanner import CorrelationScanner
        scanner = CorrelationScanner(lookback=req.lookback)
        price_series = {pair: pd.Series(prices) for pair, prices in req.price_data.items()}
        result = scanner.scan(price_series)
        if req.open_pairs:
            result["portfolio_overlap"] = scanner.check_portfolio_overlap(req.open_pairs, price_series)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# AI COACHING
# ══════════════════════════════════════════════════════════════════════════════

class CoachReq(BaseModel):
    journal_analytics: Dict
    trader_name: str = "Trader"
    experience_level: str = "Intermediate"
    primary_strategy: str = "mixed"
    account_size: float = 10_000.0

@router.post("/coach", summary="Generate AI coaching session from journal data")
async def ai_coach(req: CoachReq, user=Depends(get_current_user)):
    try:
        from coaching.ai_coach import AIPerformanceCoach
        coach = AIPerformanceCoach()
        session = await coach.coach(
            req.journal_analytics, req.trader_name,
            req.experience_level, req.primary_strategy, req.account_size,
        )
        return {
            "session_id":          session.session_id,
            "trader_summary":      session.trader_summary,
            "performance_score":   session.performance_score,
            "strengths":           session.strengths,
            "weaknesses":          session.weaknesses,
            "action_plan":         session.action_plan,
            "weekly_focus":        session.weekly_focus,
            "full_coaching_text":  session.full_coaching_text,
            "next_session_date":   session.next_session_date,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# RISK RATING
# ══════════════════════════════════════════════════════════════════════════════

class RiskRatingReq(BaseModel):
    strategy_name: str
    backtest_results: Dict
    equity_curve: Optional[List[float]] = None
    regime_breakdown: Optional[Dict[str, float]] = None

@router.post("/risk-rating", summary="Generate strategy risk rating")
async def risk_rating(req: RiskRatingReq, user=Depends(get_current_user)):
    from risk_rating.strategy_rater import StrategyRiskRater
    rater = StrategyRiskRater()
    r = rater.rate(req.strategy_name, req.backtest_results, req.equity_curve, req.regime_breakdown)
    return {
        "strategy": r.strategy_name,
        "overall_score": r.overall_score,
        "overall_grade": r.overall_grade,
        "overall_label": r.overall_label,
        "pass_for_live": r.pass_for_live,
        "summary": r.summary,
        "warnings": r.warnings,
        "strengths": r.strengths,
        "dimensions": [
            {"name": d.name, "score": d.score, "grade": d.grade, "detail": d.detail}
            for d in r.dimensions
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION TIERS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/tiers", summary="All subscription tiers and features")
async def tiers():
    from licensing.subscription_tiers import FeatureGate
    return {"tiers": FeatureGate.compare_all_tiers()}

@router.get("/tiers/my", summary="Current user's tier limits")
async def my_tier(user=Depends(get_current_user)):
    from licensing.subscription_tiers import FeatureGate
    return FeatureGate.get_limits(user.get("subscription_tier","FREE"))


# ══════════════════════════════════════════════════════════════════════════════
# PLATFORM HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/health", summary="Platform health and feature status")
async def platform_health():
    checks = {}
    modules = [
        ("strategies", "strategies"),
        ("signals", "signals.consensus_engine"),
        ("prop_firm", "prop_firm.challenge_engine"),
        ("genetic_optimizer", "evolution.genetic_optimizer"),
        ("black_swan", "black_swan.defense_system"),
        ("marketplace", "marketplace.strategy_marketplace"),
        ("signal_mirror", "mirror.signal_mirror"),
        ("mql_generator", "mql_generator.code_generator"),
        ("correlation_scanner", "correlation_scanner.scanner"),
        ("ai_coach", "coaching.ai_coach"),
        ("risk_rating", "risk_rating.strategy_rater"),
        ("subscription_tiers", "licensing.subscription_tiers"),
    ]
    for name, mod in modules:
        try:
            __import__(mod); checks[name] = "OK"
        except Exception as e:
            checks[name] = f"ERROR: {e}"

    all_ok = all(v == "OK" for v in checks.values())
    return {
        "status": "HEALTHY" if all_ok else "DEGRADED",
        "version": "GOD_LEVEL_1.0",
        "modules": checks,
        "strategy_count": 18,
        "total_api_endpoints": 28,
    }
