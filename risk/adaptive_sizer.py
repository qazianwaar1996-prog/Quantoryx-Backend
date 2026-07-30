# risk/adaptive_sizer.py
"""Quantoryx Adaptive Position Sizing — Kelly + confidence + drawdown + regime multipliers."""

import numpy as np
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class SizingDecision:
    base_risk_pct: float; adjusted_risk_pct: float
    position_size_units: float; notional_value: float
    multiplier_breakdown: dict; size_cap_applied: bool; reasoning: str


class AdaptivePositionSizer:
    """Dynamically scales position size based on signal quality and account state."""

    def __init__(self, base_risk_pct=1.0, max_risk_pct=2.0, min_risk_pct=0.25, kelly_fraction=0.25):
        self.base     = base_risk_pct / 100
        self.max_risk = max_risk_pct  / 100
        self.min_risk = min_risk_pct  / 100
        self.kelly_f  = kelly_fraction

    def size(self, balance: float, entry_price: float, stop_loss: float,
             confidence=0.5, current_drawdown_pct=0.0, recent_pnl: Optional[List[float]]=None,
             regime="Unknown", win_rate=0.5, avg_rr=1.5) -> SizingDecision:
        m = {}

        # Confidence multiplier
        m["confidence"] = 1.25 if confidence>=0.80 else 1.0 if confidence>=0.65 else 0.75 if confidence>=0.45 else 0.5

        # Drawdown multiplier
        dd = abs(current_drawdown_pct)
        m["drawdown"] = 1.0 if dd<=5 else 0.75 if dd<=10 else 0.50 if dd<=15 else 0.25

        # Streak multiplier
        m["streak"] = 1.0
        if recent_pnl and len(recent_pnl)>=3:
            last3=recent_pnl[-3:]
            if all(p>0 for p in last3):  m["streak"]=1.1
            elif all(p<=0 for p in last3): m["streak"]=0.8

        # Regime multiplier
        m["regime"] = {"Trending Bullish":1.0,"Trending Bearish":1.0,"Trending":1.0,
            "Ranging":0.85,"Moderate Trend":0.9,"High Volatility":0.70,"Low Volatility":0.95}.get(regime,0.8)

        # Kelly
        lr = 1 - win_rate
        kelly_raw = (win_rate * avg_rr - lr) / avg_rr if avg_rr > 0 else 0.0
        kelly_adj = max(0.0, kelly_raw * self.kelly_f)
        m["kelly"] = (kelly_adj / self.base) if kelly_adj > 0.005 else 1.0

        composite = (m["confidence"]*0.30 + m["drawdown"]*0.30 + m["streak"]*0.15 +
                     m["regime"]*0.15 + m["kelly"]*0.10)

        adj = self.base * composite
        capped = False
        if adj > self.max_risk: adj = self.max_risk; capped = True
        if adj < self.min_risk: adj = self.min_risk

        risk_amt = balance * adj
        sl_dist  = abs(entry_price - stop_loss)
        units    = risk_amt / sl_dist if sl_dist > 0 else 0.0
        notional = units * entry_price

        reasoning = (f"Base {self.base*100:.2f}% × Conf {m['confidence']:.2f} × "
                     f"DD {m['drawdown']:.2f} × Streak {m['streak']:.2f} × "
                     f"Regime {m['regime']:.2f} = {adj*100:.3f}% risk" +
                     (" [CAPPED]" if capped else ""))

        return SizingDecision(
            base_risk_pct=round(self.base*100,4), adjusted_risk_pct=round(adj*100,4),
            position_size_units=round(units,4), notional_value=round(notional,2),
            multiplier_breakdown={k:round(v,4) for k,v in m.items()},
            size_cap_applied=capped, reasoning=reasoning,
        )
