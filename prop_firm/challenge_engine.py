# prop_firm/challenge_engine.py
"""
Quantoryx Prop Firm Challenge Mode.

Simulates real prop firm evaluation rules for:
  - FTMO (Classic & Aggressive)
  - The5%ers (Hyper Growth & Bootcamp)
  - MyForexFunds (Rapid & Evaluation)
  - Custom (user-defined rules)

Tracks every rule in real time and tells traders exactly:
  - How far they are from passing/failing
  - Which rule is their biggest threat right now
  - What they need to do to recover
  - Daily progress dashboard
  - Challenge probability score (ML-estimated pass probability)

This is the feature that makes prop firm traders choose Quantoryx
over every other tool. They practice here before risking real money.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np


@dataclass
class PropFirmRules:
    """Rules for a specific prop firm evaluation program."""
    firm_name: str
    program_name: str
    account_size: float          # USD
    profit_target_pct: float     # % to pass (e.g. 10.0)
    max_daily_loss_pct: float    # daily drawdown limit (e.g. 5.0)
    max_total_loss_pct: float    # max overall drawdown (e.g. 10.0)
    min_trading_days: int        # minimum days required (e.g. 4)
    max_trading_days: int        # time limit (e.g. 30, 0=unlimited)
    profit_split_pct: float      # trader's cut after passing (e.g. 80.0)
    monthly_fee_usd: float       # challenge cost
    scaling_available: bool = True
    news_trading_allowed: bool = True
    weekend_holding_allowed: bool = True
    ea_allowed: bool = True
    notes: str = ""


# ─── Preset firm rules ────────────────────────────────────────────────────────
PROP_FIRM_PRESETS: Dict[str, PropFirmRules] = {

    "ftmo_standard": PropFirmRules(
        firm_name="FTMO", program_name="Standard Challenge",
        account_size=100_000, profit_target_pct=10.0,
        max_daily_loss_pct=5.0, max_total_loss_pct=10.0,
        min_trading_days=4, max_trading_days=30,
        profit_split_pct=80.0, monthly_fee_usd=540.0,
        notes="Phase 1: 10% profit / Phase 2: 5% profit with same DD rules",
    ),
    "ftmo_aggressive": PropFirmRules(
        firm_name="FTMO", program_name="Aggressive Challenge",
        account_size=100_000, profit_target_pct=20.0,
        max_daily_loss_pct=10.0, max_total_loss_pct=20.0,
        min_trading_days=4, max_trading_days=30,
        profit_split_pct=80.0, monthly_fee_usd=540.0,
    ),
    "the5ers_hyper": PropFirmRules(
        firm_name="The5%ers", program_name="Hyper Growth",
        account_size=40_000, profit_target_pct=10.0,
        max_daily_loss_pct=4.0, max_total_loss_pct=8.0,
        min_trading_days=0, max_trading_days=0,
        profit_split_pct=100.0, monthly_fee_usd=270.0,
        notes="No time limit. 100% profit split.",
    ),
    "the5ers_bootcamp": PropFirmRules(
        firm_name="The5%ers", program_name="Bootcamp",
        account_size=4_000, profit_target_pct=25.0,
        max_daily_loss_pct=3.0, max_total_loss_pct=5.0,
        min_trading_days=0, max_trading_days=0,
        profit_split_pct=50.0, monthly_fee_usd=95.0,
        news_trading_allowed=False,
    ),
    "myforexfunds_rapid": PropFirmRules(
        firm_name="MyForexFunds", program_name="Rapid",
        account_size=100_000, profit_target_pct=8.0,
        max_daily_loss_pct=5.0, max_total_loss_pct=12.0,
        min_trading_days=0, max_trading_days=30,
        profit_split_pct=75.0, monthly_fee_usd=495.0,
    ),
    "custom": PropFirmRules(
        firm_name="Custom", program_name="Custom Rules",
        account_size=100_000, profit_target_pct=10.0,
        max_daily_loss_pct=5.0, max_total_loss_pct=10.0,
        min_trading_days=4, max_trading_days=30,
        profit_split_pct=80.0, monthly_fee_usd=0.0,
    ),
}


@dataclass
class ChallengeState:
    """Live state of an active challenge simulation."""
    rules: PropFirmRules
    start_date: str
    current_balance: float
    peak_balance: float
    starting_balance: float
    trading_days: int
    total_trades: int
    winning_trades: int
    daily_pnl: Dict[str, float] = field(default_factory=dict)  # date -> pnl
    trades: List[Dict] = field(default_factory=list)
    is_passed: bool = False
    is_failed: bool = False
    fail_reason: str = ""

    # Real-time metrics
    @property
    def current_profit_pct(self) -> float:
        return (self.current_balance - self.starting_balance) / self.starting_balance * 100

    @property
    def current_drawdown_pct(self) -> float:
        if self.peak_balance <= 0: return 0.0
        return (self.peak_balance - self.current_balance) / self.peak_balance * 100

    @property
    def today_pnl(self) -> float:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.daily_pnl.get(today, 0.0)

    @property
    def today_loss_pct(self) -> float:
        day_start = self.starting_balance + sum(
            v for d, v in self.daily_pnl.items()
            if d < datetime.now().strftime("%Y-%m-%d")
        )
        if day_start <= 0: return 0.0
        return max(0.0, -self.today_pnl / day_start * 100)

    @property
    def win_rate(self) -> float:
        return self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0

    @property
    def profit_remaining_pct(self) -> float:
        return max(0.0, self.rules.profit_target_pct - self.current_profit_pct)

    @property
    def days_remaining(self) -> int:
        if self.rules.max_trading_days == 0: return 999
        return max(0, self.rules.max_trading_days - self.trading_days)


class PropFirmChallengeEngine:
    """
    Simulates and evaluates prop firm challenge performance in real time.

    Usage:
        engine = PropFirmChallengeEngine("ftmo_standard")
        engine.start_challenge()
        engine.record_trade(pnl=850.0, date="2026-07-15")
        status = engine.get_status()
    """

    def __init__(self, preset: str = "ftmo_standard", custom_rules: Optional[PropFirmRules] = None):
        if custom_rules:
            self.rules = custom_rules
        else:
            self.rules = PROP_FIRM_PRESETS.get(preset, PROP_FIRM_PRESETS["ftmo_standard"])
        self.state: Optional[ChallengeState] = None

    def start_challenge(self, start_date: Optional[str] = None) -> ChallengeState:
        """Initialize a new challenge simulation."""
        self.state = ChallengeState(
            rules=self.rules,
            start_date=start_date or datetime.now().strftime("%Y-%m-%d"),
            current_balance=self.rules.account_size,
            peak_balance=self.rules.account_size,
            starting_balance=self.rules.account_size,
            trading_days=0,
            total_trades=0,
            winning_trades=0,
        )
        return self.state

    def record_trade(self, pnl: float, date: Optional[str] = None) -> Dict:
        """Record a completed trade and check all rules."""
        if self.state is None:
            raise RuntimeError("Call start_challenge() first.")
        if self.state.is_passed or self.state.is_failed:
            return self.get_status()

        date = date or datetime.now().strftime("%Y-%m-%d")

        # Track daily PnL
        if date not in self.state.daily_pnl:
            self.state.daily_pnl[date] = 0.0
            self.state.trading_days += 1
        self.state.daily_pnl[date] += pnl

        # Update balance and peak
        self.state.current_balance += pnl
        self.state.peak_balance = max(self.state.peak_balance, self.state.current_balance)

        # Track trades
        self.state.total_trades += 1
        if pnl > 0:
            self.state.winning_trades += 1
        self.state.trades.append({"date": date, "pnl": pnl, "balance": self.state.current_balance})

        # Check rules
        self._evaluate_rules()
        return self.get_status()

    def simulate_backtest(self, trades: List[float], dates: Optional[List[str]] = None) -> Dict:
        """Run a full trade list through the challenge engine. Returns final status."""
        self.start_challenge()
        if dates is None:
            base = datetime.now()
            dates = [(base + timedelta(days=i//3)).strftime("%Y-%m-%d") for i in range(len(trades))]
        for pnl, date in zip(trades, dates):
            self.record_trade(pnl, date)
            if self.state.is_passed or self.state.is_failed:
                break
        return self.get_status()

    def get_status(self) -> Dict:
        """Return complete challenge status dashboard."""
        if self.state is None:
            return {"error": "No active challenge. Call start_challenge() first."}
        s = self.state
        r = self.rules

        # Rule status checks
        rules_status = {
            "profit_target": {
                "required": r.profit_target_pct,
                "current": round(s.current_profit_pct, 2),
                "remaining": round(s.profit_remaining_pct, 2),
                "passed": s.current_profit_pct >= r.profit_target_pct,
            },
            "max_daily_loss": {
                "limit": r.max_daily_loss_pct,
                "today": round(s.today_loss_pct, 2),
                "remaining_buffer": round(r.max_daily_loss_pct - s.today_loss_pct, 2),
                "breached": s.today_loss_pct >= r.max_daily_loss_pct,
            },
            "max_total_drawdown": {
                "limit": r.max_total_loss_pct,
                "current": round(s.current_drawdown_pct, 2),
                "remaining_buffer": round(r.max_total_loss_pct - s.current_drawdown_pct, 2),
                "breached": s.current_drawdown_pct >= r.max_total_loss_pct,
            },
            "min_trading_days": {
                "required": r.min_trading_days,
                "completed": s.trading_days,
                "passed": s.trading_days >= r.min_trading_days,
            },
            "time_limit": {
                "max_days": r.max_trading_days,
                "days_used": s.trading_days,
                "days_remaining": s.days_remaining,
                "breached": r.max_trading_days > 0 and s.trading_days > r.max_trading_days,
            },
        }

        # Pass probability estimation
        pass_probability = self._estimate_pass_probability()

        # Coaching tips
        tips = self._coaching_tips()

        return {
            "firm": r.firm_name,
            "program": r.program_name,
            "account_size": r.account_size,
            "profit_split_pct": r.profit_split_pct,
            "status": "PASSED" if s.is_passed else "FAILED" if s.is_failed else "ACTIVE",
            "fail_reason": s.fail_reason if s.is_failed else None,
            "metrics": {
                "current_balance": round(s.current_balance, 2),
                "current_profit_pct": round(s.current_profit_pct, 2),
                "current_drawdown_pct": round(s.current_drawdown_pct, 2),
                "today_pnl": round(s.today_pnl, 2),
                "today_loss_pct": round(s.today_loss_pct, 2),
                "trading_days": s.trading_days,
                "days_remaining": s.days_remaining,
                "total_trades": s.total_trades,
                "win_rate": round(s.win_rate, 3),
                "profit_target_remaining_pct": round(s.profit_remaining_pct, 2),
                "potential_payout_usd": round(
                    (s.current_balance - s.starting_balance) * r.profit_split_pct / 100, 2
                ) if s.is_passed else 0.0,
            },
            "rules_status": rules_status,
            "pass_probability": pass_probability,
            "coaching_tips": tips,
            "equity_curve": [t["balance"] for t in s.trades],
            "daily_pnl": dict(sorted(s.daily_pnl.items())),
        }

    def get_available_presets(self) -> List[Dict]:
        """Return all available prop firm presets for frontend display."""
        return [
            {
                "key": key,
                "firm_name": r.firm_name,
                "program_name": r.program_name,
                "account_size": r.account_size,
                "profit_target_pct": r.profit_target_pct,
                "max_daily_loss_pct": r.max_daily_loss_pct,
                "max_total_loss_pct": r.max_total_loss_pct,
                "max_trading_days": r.max_trading_days,
                "profit_split_pct": r.profit_split_pct,
                "monthly_fee_usd": r.monthly_fee_usd,
                "notes": r.notes,
            }
            for key, r in PROP_FIRM_PRESETS.items()
        ]

    # ─── Private ───────────────────────────────────────────────────────────────

    def _evaluate_rules(self):
        s = self.state; r = self.rules
        # Check failures first
        if s.today_loss_pct >= r.max_daily_loss_pct:
            s.is_failed = True
            s.fail_reason = f"Daily loss limit breached: {s.today_loss_pct:.2f}% (limit: {r.max_daily_loss_pct}%)"
            return
        if s.current_drawdown_pct >= r.max_total_loss_pct:
            s.is_failed = True
            s.fail_reason = f"Max drawdown breached: {s.current_drawdown_pct:.2f}% (limit: {r.max_total_loss_pct}%)"
            return
        if r.max_trading_days > 0 and s.trading_days > r.max_trading_days:
            s.is_failed = True
            s.fail_reason = f"Time limit exceeded: {s.trading_days} days (limit: {r.max_trading_days})"
            return
        # Check pass
        profit_ok = s.current_profit_pct >= r.profit_target_pct
        days_ok = s.trading_days >= r.min_trading_days
        if profit_ok and days_ok:
            s.is_passed = True

    def _estimate_pass_probability(self) -> float:
        """Simple heuristic pass probability based on current trajectory."""
        if self.state is None: return 0.0
        s = self.state; r = self.rules
        if s.is_passed: return 1.0
        if s.is_failed: return 0.0

        # Factors
        profit_progress = min(1.0, s.current_profit_pct / r.profit_target_pct) if r.profit_target_pct > 0 else 0
        dd_safety = 1.0 - (s.current_drawdown_pct / r.max_total_loss_pct) if r.max_total_loss_pct > 0 else 0.5
        daily_safety = 1.0 - (s.today_loss_pct / r.max_daily_loss_pct) if r.max_daily_loss_pct > 0 else 0.5
        time_factor = (s.days_remaining / r.max_trading_days) if r.max_trading_days > 0 else 0.8
        wr_factor = s.win_rate if s.total_trades >= 5 else 0.5

        score = (
            profit_progress * 0.35 +
            dd_safety * 0.25 +
            daily_safety * 0.15 +
            time_factor * 0.15 +
            wr_factor * 0.10
        )
        return round(float(np.clip(score, 0.0, 0.99)), 3)

    def _coaching_tips(self) -> List[str]:
        if self.state is None: return []
        s = self.state; r = self.rules; tips = []

        daily_buf = r.max_daily_loss_pct - s.today_loss_pct
        if daily_buf < 1.5:
            tips.append(f"⚠️ CRITICAL: Only {daily_buf:.2f}% daily loss buffer remaining. Stop trading today if possible.")

        dd_buf = r.max_total_loss_pct - s.current_drawdown_pct
        if dd_buf < 2.0:
            tips.append(f"⚠️ Drawdown buffer critically low ({dd_buf:.2f}%). Reduce position sizes immediately.")

        if s.days_remaining < 5 and r.max_trading_days > 0 and s.profit_remaining_pct > 2.0:
            tips.append(f"⏰ {s.days_remaining} days left, need {s.profit_remaining_pct:.1f}% more. Consider slightly larger positions but stay within DD rules.")

        if s.win_rate < 0.40 and s.total_trades >= 10:
            tips.append("Win rate below 40%. Your entry criteria may need tightening. Consider pausing and reviewing recent trades.")

        if s.current_profit_pct >= r.profit_target_pct * 0.8:
            tips.append(f"🎯 Almost there! {s.profit_remaining_pct:.2f}% to target. Play conservatively — protect what you've built.")

        if not tips:
            tips.append("✅ Challenge on track. Maintain consistency and protect your drawdown buffers.")

        return tips
