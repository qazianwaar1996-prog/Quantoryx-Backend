# analytics/portfolio_intelligence.py
"""Quantoryx Portfolio Intelligence — Correlation, Kelly allocation, circuit breakers."""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class StrategyAllocation:
    strategy: str; allocation_pct: float; allocation_usd: float
    kelly_fraction: float; is_active: bool = True
    pause_reason: Optional[str] = None; current_drawdown_pct: float = 0.0
    win_rate: float = 0.0; avg_rr: float = 0.0


@dataclass
class PortfolioSnapshot:
    total_capital: float; deployed_capital: float; available_capital: float
    portfolio_heat: float; active_strategies: int; paused_strategies: int
    allocations: List[StrategyAllocation]
    correlation_matrix: Dict; diversification_score: float; risk_budget_used_pct: float


class PortfolioIntelligenceEngine:
    """Kelly + correlation-adjusted capital allocation with drawdown circuit breakers."""

    def __init__(self, total_capital=100_000.0, max_strategy_drawdown=15.0,
                 kelly_fraction=0.25, min_alloc_pct=2.0, max_alloc_pct=40.0):
        self.total_capital = total_capital
        self.max_dd        = max_strategy_drawdown / 100
        self.kelly_frac    = kelly_fraction
        self.min_alloc     = min_alloc_pct / 100
        self.max_alloc     = max_alloc_pct / 100
        self._paused: Dict[str, str] = {}

    def analyze(self, strategy_returns: Dict[str, pd.Series],
                current_drawdowns: Optional[Dict[str, float]] = None) -> PortfolioSnapshot:
        current_drawdowns = current_drawdowns or {}
        corr = self._correlation_matrix(strategy_returns)
        kelly = {n: self._kelly(r) for n, r in strategy_returns.items()}
        allocs = self._correlation_adjusted(kelly, corr)
        allocations = []
        for name, pct in allocs.items():
            dd = current_drawdowns.get(name, 0.0) / 100
            active = True; reason = None
            if name in self._paused:
                active = False; reason = self._paused[name]
            elif dd >= self.max_dd:
                active = False; reason = f"DD {dd*100:.1f}% > limit {self.max_dd*100:.0f}%"
                self._paused[name] = reason
            wr, rr = self._wr_rr(strategy_returns.get(name, pd.Series(dtype=float)))
            allocations.append(StrategyAllocation(
                strategy=name, allocation_pct=round(pct*100,2) if active else 0.0,
                allocation_usd=round(pct*self.total_capital,2) if active else 0.0,
                kelly_fraction=round(kelly.get(name,0.0),4), is_active=active,
                pause_reason=reason, current_drawdown_pct=round(dd*100,2),
                win_rate=round(wr,4), avg_rr=round(rr,2),
            ))
        active_a = [a for a in allocations if a.is_active]
        deployed = sum(a.allocation_usd for a in active_a)
        div      = self._div_score(corr)
        return PortfolioSnapshot(
            total_capital=self.total_capital, deployed_capital=round(deployed,2),
            available_capital=round(self.total_capital-deployed,2),
            portfolio_heat=round(len(active_a)*0.5,2),
            active_strategies=len(active_a), paused_strategies=len(allocations)-len(active_a),
            allocations=allocations,
            correlation_matrix={n:{m:round(float(corr.loc[n,m]),3) for m in corr.columns}
                                 for n in corr.index} if not corr.empty else {},
            diversification_score=round(div,4), risk_budget_used_pct=round(deployed/self.total_capital*100,2),
        )

    def rank_strategies(self, strategy_returns: Dict[str, pd.Series]) -> List[Dict]:
        result = []
        for name, r in strategy_returns.items():
            if len(r)<5: continue
            m=float(r.mean()); s=float(r.std())
            sharpe=m/s if s>0 else 0.0; wr,rr=self._wr_rr(r)
            result.append({"strategy":name,"sharpe":round(sharpe,4),"win_rate":round(wr,4),
                           "avg_rr":round(rr,2),"total_pnl":round(float(r.sum()),2),"trades":len(r)})
        return sorted(result, key=lambda x: x["sharpe"], reverse=True)

    def _kelly(self, r: pd.Series) -> float:
        if len(r)<5: return 0.0
        wr=float((r>0).mean()); lr=1-wr
        aw=float(r[r>0].mean()) if (r>0).any() else 0.0
        al=float(abs(r[r<=0].mean())) if (r<=0).any() else 1.0
        rr=aw/al if al>0 else 0.0
        if rr==0: return 0.0
        raw=(wr*rr-lr)/rr * self.kelly_frac
        return float(np.clip(raw, self.min_alloc, self.max_alloc))

    def _correlation_matrix(self, strategy_returns: Dict[str, pd.Series]) -> pd.DataFrame:
        if not strategy_returns: return pd.DataFrame()
        ml=max(len(s) for s in strategy_returns.values())
        aligned={n:s.reset_index(drop=True).reindex(range(ml)).fillna(0) for n,s in strategy_returns.items()}
        df=pd.DataFrame(aligned)
        return df.corr() if len(df)>1 else pd.DataFrame()

    def _correlation_adjusted(self, kelly: Dict[str,float], corr: pd.DataFrame) -> Dict[str,float]:
        allocs=dict(kelly)
        if not corr.empty:
            keys=list(allocs)
            for i in range(len(keys)):
                for j in range(i+1,len(keys)):
                    p1,p2=keys[i],keys[j]
                    if p1 in corr.index and p2 in corr.columns:
                        c=abs(float(corr.loc[p1,p2]))
                        if c>0.7:
                            pen=1-(c-0.7)*2
                            allocs[p1]*=pen; allocs[p2]*=pen
        total=sum(allocs.values())
        if total>1.0: allocs={k:v/total for k,v in allocs.items()}
        return allocs

    def _div_score(self, corr: pd.DataFrame) -> float:
        if corr.empty or len(corr)<=1: return 1.0
        n=len(corr); off=corr.values-np.eye(n)
        return float(1-abs(off).mean())

    def _wr_rr(self, r: pd.Series) -> Tuple[float,float]:
        if len(r)==0: return 0.0,0.0
        wr=float((r>0).mean())
        aw=float(r[r>0].mean()) if (r>0).any() else 0.0
        al=float(abs(r[r<=0].mean())) if (r<=0).any() else 1.0
        return wr, aw/al if al>0 else 0.0
