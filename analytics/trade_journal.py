# analytics/trade_journal.py
"""
Quantoryx Trade Journal Analytics Engine.
Surfaces actionable insights from trade history including behaviour flags,
time-of-day patterns, strategy rankings, and personalized tips.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional


@dataclass
class TradeRecord:
    trade_id: str; user_id: str; strategy: str; pair: str
    direction: str; entry_price: float; exit_price: float
    stop_loss: float; take_profit: float; position_size: float
    pnl: float; pnl_pct: float; entry_time: str; exit_time: str
    duration_minutes: int; regime: str = "Unknown"; timeframe: str = "H1"
    confidence: float = 0.5; exit_reason: str = "MANUAL"; notes: str = ""


class TradeJournalAnalytics:
    def __init__(self, trades: List[TradeRecord]):
        self.trades = trades
        self._df: Optional[pd.DataFrame] = None
        if trades:
            self._df = pd.DataFrame([asdict(t) for t in trades])

    def full_report(self) -> Dict:
        if not self.trades or self._df is None:
            return {"error": "No trades in journal."}
        return {
            "summary":           self.summary_stats(),
            "by_strategy":       self._group("strategy"),
            "by_pair":           self._group("pair"),
            "by_regime":         self._group("regime"),
            "by_hour":           self.by_hour(),
            "by_day_of_week":    self.by_day_of_week(),
            "by_session":        self.by_session(),
            "streak_analysis":   self.streak_analysis(),
            "drawdown_analysis": self.drawdown_analysis(),
            "behaviour_flags":   self.behaviour_flags(),
            "best_worst_trades": self.best_worst_trades(),
            "improvement_tips":  self.improvement_tips(),
        }

    def summary_stats(self) -> Dict:
        df   = self._df
        wins = df[df["pnl"] > 0]; losses = df[df["pnl"] <= 0]
        total = len(df); wr = len(wins) / total if total > 0 else 0.0
        gp = wins["pnl"].sum(); gl = abs(losses["pnl"].sum())
        pf = gp / gl if gl > 0 else float("inf")
        aw = wins["pnl"].mean() if len(wins) > 0 else 0.0
        al = losses["pnl"].mean() if len(losses) > 0 else 0.0
        rr = abs(aw / al) if al != 0 else 0.0
        eq = df["pnl"].cumsum(); pk = eq.cummax()
        dd = ((eq - pk) / pk.abs().replace(0, np.nan)).fillna(0).min()
        return {
            "total_trades": total, "wins": len(wins), "losses": len(losses),
            "win_rate": round(wr, 4), "profit_factor": round(pf, 2),
            "avg_win_pnl": round(aw, 2), "avg_loss_pnl": round(al, 2),
            "risk_reward_ratio": round(rr, 2), "total_pnl": round(df["pnl"].sum(), 2),
            "max_drawdown_pct": round(float(dd) * 100, 2),
            "avg_duration_min": round(df["duration_minutes"].mean(), 1),
            "avg_confidence": round(df["confidence"].mean(), 3),
        }

    def by_hour(self) -> List[Dict]:
        df = self._df.copy()
        df["hour"] = pd.to_datetime(df["entry_time"]).dt.hour
        return [{"hour": int(h), "trades": len(g), "win_rate": round((g["pnl"]>0).mean(),4),
                 "avg_pnl": round(g["pnl"].mean(),2), "total_pnl": round(g["pnl"].sum(),2)}
                for h, g in df.groupby("hour")]

    def by_day_of_week(self) -> List[Dict]:
        df = self._df.copy()
        df["dow"] = pd.to_datetime(df["entry_time"]).dt.day_name()
        order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        return [{"day": d, "trades": len(g), "win_rate": round((g["pnl"]>0).mean(),4),
                 "avg_pnl": round(g["pnl"].mean(),2), "total_pnl": round(g["pnl"].sum(),2)}
                for d in order if (g := df[df["dow"]==d]) is not None and len(g) > 0]

    def by_session(self) -> List[Dict]:
        df = self._df.copy()
        df["hour"] = pd.to_datetime(df["entry_time"]).dt.hour
        sessions = {"Sydney":(21,6),"Tokyo":(0,9),"London":(7,16),"New York":(13,22)}
        result = []
        for name, (s, e) in sessions.items():
            mask = (df["hour"]>=s)&(df["hour"]<e) if s<e else (df["hour"]>=s)|(df["hour"]<e)
            g = df[mask]
            if len(g): result.append({"session":name,"trades":len(g),
                "win_rate":round((g["pnl"]>0).mean(),4),"total_pnl":round(g["pnl"].sum(),2)})
        return result

    def streak_analysis(self) -> Dict:
        results = [1 if p > 0 else -1 for p in self._df["pnl"]]
        mw=ml=cw=cl=0
        for r in results:
            if r > 0: cw+=1; cl=0; mw=max(mw,cw)
            else:     cl+=1; cw=0; ml=max(ml,cl)
        return {"max_win_streak":mw,"max_loss_streak":ml,"current_streak":cw if cw>0 else -cl}

    def drawdown_analysis(self) -> Dict:
        eq = self._df["pnl"].cumsum()
        dd = eq - eq.cummax()
        return {"max_drawdown_pnl":round(float(dd.min()),2),
                "equity_curve":[round(v,2) for v in eq.tolist()]}

    def behaviour_flags(self) -> List[Dict]:
        flags = []; df = self._df.copy()
        df["entry_dt"] = pd.to_datetime(df["entry_time"])
        df = df.sort_values("entry_dt")
        # Revenge trading
        revenge = sum(1 for i in range(1,len(df))
            if df["pnl"].iloc[i-1]<0 and
               0<(pd.to_datetime(df["entry_time"].iloc[i])-pd.to_datetime(df["exit_time"].iloc[i-1])).total_seconds()/60<5)
        if revenge: flags.append({"flag":"REVENGE_TRADING","severity":"HIGH","count":revenge,
            "description":f"{revenge} trade(s) opened <5 min after a loss. Add a cooldown rule."})
        # Overtrading
        df["date"]=df["entry_dt"].dt.date; heavy=int((df.groupby("date").size()>10).sum())
        if heavy: flags.append({"flag":"OVERTRADING","severity":"MEDIUM","count":heavy,
            "description":f"Traded >10 times on {heavy} day(s). Quality over quantity."})
        return flags

    def best_worst_trades(self) -> Dict:
        df = self._df
        return {"best_trade":df.loc[df["pnl"].idxmax()].to_dict(),
                "worst_trade":df.loc[df["pnl"].idxmin()].to_dict()}

    def improvement_tips(self) -> List[str]:
        tips = []; s = self.summary_stats()
        if s["win_rate"] < 0.45: tips.append("Win rate below 45% — tighten entry criteria.")
        if s["risk_reward_ratio"] < 1.5: tips.append("R:R below 1.5 — widen take-profits or tighten stops.")
        bh = self.by_hour()
        if bh:
            best=max(bh,key=lambda x:x["win_rate"]); worst=min(bh,key=lambda x:x["win_rate"])
            if best["win_rate"]>0.6: tips.append(f"Best hour: {best['hour']}:00 UTC ({best['win_rate']*100:.0f}% WR).")
            if worst["win_rate"]<0.35: tips.append(f"Avoid {worst['hour']}:00 UTC ({worst['win_rate']*100:.0f}% WR).")
        bs = self._group("strategy")
        if bs:
            best=bs[0]; worst=bs[-1]
            if best.get("trades",0)>=10: tips.append(f"{best['name']} is your best strategy ({best['win_rate']*100:.0f}% WR).")
        return tips or ["Keep trading consistently and tracking your journal."]

    def _group(self, col: str) -> List[Dict]:
        df = self._df; result = []
        for name, g in df.groupby(col):
            wins=g[g["pnl"]>0]; losses=g[g["pnl"]<=0]
            gp=wins["pnl"].sum(); gl=abs(losses["pnl"].sum())
            result.append({"name":str(name),"trades":len(g),"win_rate":round((g["pnl"]>0).mean(),4),
                "avg_pnl":round(g["pnl"].mean(),2),"total_pnl":round(g["pnl"].sum(),2),
                "profit_factor":round(gp/gl if gl>0 else 0,2)})
        return sorted(result, key=lambda x: x["total_pnl"], reverse=True)
