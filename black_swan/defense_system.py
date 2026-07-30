# black_swan/defense_system.py
"""
Quantoryx Black Swan Defense System.

Monitors live market conditions for systemic shock events and
automatically triggers protective actions before accounts blow up.

Detection layers:
  1. Volatility spike monitor (ATR expansion > N× normal)
  2. Flash crash detector (price moves > X% in < Y candles)
  3. Spread explosion monitor (spread > N× normal = broker stress)
  4. Correlation breakdown (all pairs moving together = systemic event)
  5. Liquidity drought (volume collapses = thin market danger)

Protective actions (in escalating order):
  LEVEL 1 — CAUTION:    Reduce all position sizes by 50%
  LEVEL 2 — DEFENSIVE:  Close all pending orders, tighten stops
  LEVEL 3 — SHIELD:     Close all trades, halt new signals 30 min
  LEVEL 4 — LOCKDOWN:   Emergency close all + alert user + freeze platform
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional
import numpy as np
import pandas as pd

from utils.logging_config import get_logger
logger = get_logger("black_swan.defense_system")


@dataclass
class ThreatLevel:
    level: int               # 0=clear, 1=caution, 2=defensive, 3=shield, 4=lockdown
    label: str
    color: str               # for frontend UI
    triggered_by: List[str]
    recommended_action: str
    auto_execute: bool       # whether to act without user confirmation


@dataclass
class MarketHealthSnapshot:
    timestamp: str
    threat_level: ThreatLevel
    vol_ratio: float          # current ATR / normal ATR
    spread_ratio: float       # current spread / normal spread
    flash_crash_detected: bool
    correlation_spike: float  # 0–1 cross-pair correlation
    volume_ratio: float       # current volume / normal volume
    active_alerts: List[str]
    is_locked_down: bool


THREAT_LEVELS = {
    0: ThreatLevel(0, "CLEAR",     "#22c55e", [], "Normal trading.",                          False),
    1: ThreatLevel(1, "CAUTION",   "#f59e0b", [], "Reduce position sizes by 50%.",            False),
    2: ThreatLevel(2, "DEFENSIVE", "#f97316", [], "Close pending orders. Tighten all stops.", False),
    3: ThreatLevel(3, "SHIELD",    "#ef4444", [], "Close all trades. Halt signals 30 min.",   True),
    4: ThreatLevel(4, "LOCKDOWN",  "#7c3aed", [], "Emergency close ALL. Freeze platform.",    True),
}


class BlackSwanDefenseSystem:
    """
    Autonomous market shock protection system.

    Continuously evaluates market health metrics and escalates
    threat levels automatically, triggering protective actions
    when thresholds are breached.

    Usage:
        defense = BlackSwanDefenseSystem()
        defense.set_alert_callback(my_alert_fn)
        snapshot = defense.evaluate(df_eurusd, df_gbpusd, df_usdjpy)
        if snapshot.threat_level.level >= 3:
            # platform auto-closes all trades
    """

    def __init__(
        self,
        vol_caution_ratio:    float = 2.5,   # ATR 2.5× normal → caution
        vol_shield_ratio:     float = 4.0,   # ATR 4× normal → shield
        vol_lockdown_ratio:   float = 6.0,   # ATR 6× normal → lockdown
        flash_crash_pct:      float = 1.5,   # 1.5% move in 3 candles → flash crash
        flash_crash_candles:  int   = 3,
        spread_caution_ratio: float = 3.0,
        spread_lockdown_ratio:float = 8.0,
        corr_spike_threshold: float = 0.90,  # all pairs > 90% corr = systemic
        vol_baseline_period:  int   = 100,   # candles for baseline
        alert_callback: Optional[Callable] = None,
    ):
        self.vol_caution     = vol_caution_ratio
        self.vol_shield      = vol_shield_ratio
        self.vol_lockdown    = vol_lockdown_ratio
        self.flash_pct       = flash_crash_pct / 100
        self.flash_candles   = flash_crash_candles
        self.spread_caution  = spread_caution_ratio
        self.spread_lockdown = spread_lockdown_ratio
        self.corr_spike_th   = corr_spike_threshold
        self.baseline_period = vol_baseline_period
        self._alert_fn       = alert_callback
        self._is_locked      = False
        self._lockdown_until: Optional[datetime] = None
        self._history: List[MarketHealthSnapshot] = []

    def set_alert_callback(self, fn: Callable):
        """Register an async/sync function to call on threat escalation."""
        self._alert_fn = fn

    def evaluate(self, *pair_dfs: pd.DataFrame, spreads: Optional[Dict[str, float]] = None) -> MarketHealthSnapshot:
        """
        Evaluate market health across multiple pair DataFrames.
        Each df must have: open, high, low, close, volume columns.
        """
        now = datetime.now(timezone.utc).isoformat()
        alerts: List[str] = []
        max_threat = 0

        vol_ratio    = 1.0
        spread_ratio = 1.0
        vol_ratio_v  = 1.0
        flash        = False
        corr_spike   = 0.0

        for df in pair_dfs:
            if df is None or len(df) < self.baseline_period:
                continue

            c = df["close"] if "close" in df.columns else df["Close"]
            h = df["high"]  if "high"  in df.columns else df["High"]
            l = df["low"]   if "low"   in df.columns else df["Low"]

            # ── ATR volatility ratio ──────────────────────────────────
            pc = c.shift(1)
            tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
            atr_now      = float(tr.iloc[-self.flash_candles:].mean())
            atr_baseline = float(tr.iloc[-self.baseline_period:-self.flash_candles].mean())
            if atr_baseline > 0:
                ratio = atr_now / atr_baseline
                vol_ratio = max(vol_ratio, ratio)
                if ratio >= self.vol_lockdown:
                    alerts.append(f"VOLATILITY LOCKDOWN: ATR {ratio:.1f}× normal")
                    max_threat = max(max_threat, 4)
                elif ratio >= self.vol_shield:
                    alerts.append(f"VOLATILITY SHIELD: ATR {ratio:.1f}× normal")
                    max_threat = max(max_threat, 3)
                elif ratio >= self.vol_caution:
                    alerts.append(f"VOLATILITY CAUTION: ATR {ratio:.1f}× normal")
                    max_threat = max(max_threat, 1)

            # ── Flash crash detector ──────────────────────────────────
            recent_move = abs(float(c.iloc[-1]) - float(c.iloc[-self.flash_candles])) / float(c.iloc[-self.flash_candles])
            if recent_move >= self.flash_pct:
                flash = True
                alerts.append(f"FLASH CRASH DETECTED: {recent_move*100:.2f}% in {self.flash_candles} candles")
                max_threat = max(max_threat, 3)

            # ── Volume drought ────────────────────────────────────────
            if "volume" in df.columns and df["volume"].sum() > 0:
                vol_now  = float(df["volume"].iloc[-5:].mean())
                vol_base = float(df["volume"].iloc[-self.baseline_period:-5].mean())
                if vol_base > 0:
                    vr = vol_now / vol_base
                    vol_ratio_v = min(vol_ratio_v, vr)
                    if vr < 0.2:
                        alerts.append(f"LIQUIDITY DROUGHT: Volume at {vr*100:.0f}% of normal")
                        max_threat = max(max_threat, 2)

        # ── Cross-pair correlation spike ──────────────────────────────
        if len(pair_dfs) >= 2:
            corr_series = []
            for df in pair_dfs:
                if df is None or len(df) < 20: continue
                c = df["close"] if "close" in df.columns else df["Close"]
                corr_series.append(c.pct_change().iloc[-20:].reset_index(drop=True))
            if len(corr_series) >= 2:
                corr_df  = pd.DataFrame(corr_series).T.dropna()
                if not corr_df.empty and len(corr_df) > 2:
                    corr_mat = corr_df.corr()
                    n = len(corr_mat)
                    off_diag = [(corr_mat.iloc[i,j]) for i in range(n) for j in range(i+1,n)]
                    if off_diag:
                        corr_spike = float(np.mean([abs(v) for v in off_diag]))
                        if corr_spike >= self.corr_spike_th:
                            alerts.append(f"SYSTEMIC EVENT: All pairs {corr_spike:.0%} correlated")
                            max_threat = max(max_threat, 3)

        # ── Spread monitor ────────────────────────────────────────────
        if spreads:
            for pair, sp in spreads.items():
                if sp > 0:
                    normal_spread = {"EURUSD": 0.0001, "GBPUSD": 0.0002}.get(pair, 0.0002)
                    sr = sp / normal_spread
                    spread_ratio = max(spread_ratio, sr)
                    if sr >= self.spread_lockdown:
                        alerts.append(f"SPREAD LOCKDOWN: {pair} spread {sr:.0f}× normal")
                        max_threat = max(max_threat, 4)
                    elif sr >= self.spread_caution:
                        alerts.append(f"SPREAD CAUTION: {pair} spread {sr:.0f}× normal")
                        max_threat = max(max_threat, 1)

        # ── Active lockdown check ─────────────────────────────────────
        if self._is_locked and self._lockdown_until:
            if datetime.now(timezone.utc) < self._lockdown_until:
                max_threat = max(max_threat, 3)
                alerts.insert(0, f"PLATFORM LOCKED until {self._lockdown_until.isoformat()}")
            else:
                self._is_locked = False
                self._lockdown_until = None
                logger.info("BlackSwan lockdown lifted.")

        # Escalate lockdown if level 4
        if max_threat >= 4 and not self._is_locked:
            from datetime import timedelta
            self._is_locked = True
            self._lockdown_until = datetime.now(timezone.utc) + timedelta(minutes=60)
            logger.critical("BLACK SWAN LOCKDOWN ACTIVATED")

        threat = THREAT_LEVELS[min(max_threat, 4)]
        threat.triggered_by = alerts[:3]

        snapshot = MarketHealthSnapshot(
            timestamp=now,
            threat_level=threat,
            vol_ratio=round(vol_ratio, 2),
            spread_ratio=round(spread_ratio, 2),
            flash_crash_detected=flash,
            correlation_spike=round(corr_spike, 3),
            volume_ratio=round(vol_ratio_v, 2),
            active_alerts=alerts,
            is_locked_down=self._is_locked,
        )

        self._history.append(snapshot)

        if alerts and self._alert_fn:
            try:
                self._alert_fn(snapshot)
            except Exception as e:
                logger.error("Alert callback error: %s", e)

        return snapshot

    def emergency_unlock(self) -> str:
        """Manually lift a lockdown (requires user confirmation in UI)."""
        self._is_locked = False
        self._lockdown_until = None
        logger.warning("BlackSwan lockdown manually lifted by user.")
        return "Lockdown lifted. Trading resumed with caution."

    def get_health_history(self) -> List[Dict]:
        return [
            {
                "timestamp": s.timestamp,
                "threat_level": s.threat_level.level,
                "label": s.threat_level.label,
                "vol_ratio": s.vol_ratio,
                "flash_crash": s.flash_crash_detected,
                "alerts": s.active_alerts,
            }
            for s in self._history[-50:]
        ]
