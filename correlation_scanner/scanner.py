# correlation_scanner/scanner.py
"""
Quantoryx Real-Time Correlation Scanner.

Scans 28+ forex pairs simultaneously and surfaces:
  - Live correlation matrix (color-coded)
  - Pairs moving in sync right now (hidden risk exposure)
  - Diverging pairs (potential mean-reversion opportunity)
  - Portfolio overlap warnings (you're trading the same market twice)
  - Correlation regime shifts (correlations breaking down)
  - Best uncorrelated pairs for diversification
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import pandas as pd
from datetime import datetime, timezone


ALL_PAIRS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD",
    "EURJPY","GBPJPY","EURGBP","AUDJPY","EURAUD","EURCHF","AUDCAD",
    "GBPCHF","CADJPY","GBPCAD","AUDCHF","NZDJPY","EURCAD",
    "XAUUSD","XAGUSD",
]

@dataclass
class CorrelationAlert:
    pair1: str
    pair2: str
    correlation: float
    alert_type: str        # "HIGH_CORR" | "ANTI_CORR" | "REGIME_SHIFT"
    severity: str          # "WARNING" | "CRITICAL"
    message: str


class CorrelationScanner:
    """
    Real-time correlation analysis across forex pairs.

    Usage:
        scanner = CorrelationScanner()
        result = scanner.scan(price_data_dict, lookback=20)
        warnings = scanner.check_portfolio_overlap(["EURUSD","GBPUSD"])
    """

    HIGH_CORR_THRESHOLD  = 0.80
    ANTI_CORR_THRESHOLD  = -0.70
    REGIME_SHIFT_DELTA   = 0.30   # correlation moved >30% = regime shift

    def __init__(self, lookback: int = 20, long_lookback: int = 100):
        self.lookback      = lookback
        self.long_lookback = long_lookback
        self._last_corr: Optional[pd.DataFrame] = None
        self._prev_corr: Optional[pd.DataFrame] = None

    def scan(self, price_data: Dict[str, pd.Series]) -> Dict:
        """
        Run correlation scan on latest prices.

        price_data: {pair_name: pd.Series of closing prices}
        Returns full scan result with matrix, alerts, recommendations.
        """
        if len(price_data) < 2:
            return {"error": "Need at least 2 pairs for correlation analysis."}

        # Build returns DataFrame
        returns = pd.DataFrame({
            pair: prices.pct_change().dropna()
            for pair, prices in price_data.items()
            if len(prices) >= self.lookback
        }).dropna()

        if returns.empty or len(returns) < 5:
            return {"error": "Insufficient data for correlation."}

        short_ret = returns.iloc[-self.lookback:]
        long_ret  = returns.iloc[-self.long_lookback:] if len(returns) >= self.long_lookback else returns

        short_corr = short_ret.corr()
        long_corr  = long_ret.corr()

        # Save for regime shift detection
        self._prev_corr = self._last_corr
        self._last_corr = short_corr

        # Build alerts
        alerts    = self._detect_alerts(short_corr, long_corr)
        top_corr  = self._top_correlations(short_corr)
        best_divs = self._best_diversifiers(short_corr)

        return {
            "timestamp":          datetime.now(timezone.utc).isoformat(),
            "pairs_scanned":      list(returns.columns),
            "lookback_bars":      self.lookback,
            "correlation_matrix": self._matrix_to_dict(short_corr),
            "long_term_matrix":   self._matrix_to_dict(long_corr),
            "top_correlations":   top_corr,
            "best_diversifiers":  best_divs,
            "alerts":             [
                {"pair1": a.pair1, "pair2": a.pair2, "correlation": round(a.correlation, 3),
                 "type": a.alert_type, "severity": a.severity, "message": a.message}
                for a in alerts
            ],
            "alert_count":        len(alerts),
            "critical_count":     sum(1 for a in alerts if a.severity == "CRITICAL"),
        }

    def check_portfolio_overlap(self, open_pairs: List[str], price_data: Dict[str, pd.Series]) -> Dict:
        """
        Check if a trader's current open positions are highly correlated.
        Warns when they're unknowingly doubling up on the same market.
        """
        if len(open_pairs) < 2:
            return {"overlap_risk": "LOW", "warnings": []}

        filtered = {p: v for p, v in price_data.items() if p in open_pairs}
        scan = self.scan(filtered)
        if "error" in scan:
            return {"overlap_risk": "UNKNOWN", "warnings": []}

        warnings = []
        for alert in scan.get("alerts", []):
            if alert["type"] == "HIGH_CORR":
                warnings.append(
                    f"⚠️ {alert['pair1']} and {alert['pair2']} are {alert['correlation']*100:.0f}% correlated. "
                    "You're effectively doubling your exposure."
                )

        overlap_risk = "CRITICAL" if scan["critical_count"] > 0 else \
                       "HIGH" if scan["alert_count"] > 2 else \
                       "MEDIUM" if scan["alert_count"] > 0 else "LOW"

        return {
            "overlap_risk":     overlap_risk,
            "open_pairs":       open_pairs,
            "warnings":         warnings,
            "effective_exposure": f"Your {len(open_pairs)} positions may behave like {max(1,len(open_pairs)-scan['critical_count'])} positions due to correlation.",
        }

    def get_pair_correlation(self, pair1: str, pair2: str, price_data: Dict) -> Dict:
        """Get the correlation between exactly two pairs."""
        if pair1 not in price_data or pair2 not in price_data:
            return {"error": "One or both pairs not in price data."}
        r1 = price_data[pair1].pct_change().dropna()
        r2 = price_data[pair2].pct_change().dropna()
        aligned = pd.DataFrame({"a": r1, "b": r2}).dropna()
        if len(aligned) < 5:
            return {"error": "Insufficient data."}
        corr = float(aligned["a"].corr(aligned["b"]))
        label = ("Strong positive" if corr > 0.7 else
                 "Moderate positive" if corr > 0.3 else
                 "Weak/No" if corr > -0.3 else
                 "Moderate negative" if corr > -0.7 else "Strong negative")
        return {
            "pair1": pair1, "pair2": pair2,
            "correlation": round(corr, 4),
            "label": label,
            "bars_used": len(aligned),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _detect_alerts(self, short: pd.DataFrame, long: pd.DataFrame) -> List[CorrelationAlert]:
        alerts = []
        pairs  = list(short.columns)
        for i in range(len(pairs)):
            for j in range(i+1, len(pairs)):
                p1, p2 = pairs[i], pairs[j]
                if p1 not in short.index or p2 not in short.columns:
                    continue
                sc = float(short.loc[p1, p2])

                if sc >= self.HIGH_CORR_THRESHOLD:
                    alerts.append(CorrelationAlert(
                        pair1=p1, pair2=p2, correlation=sc,
                        alert_type="HIGH_CORR",
                        severity="CRITICAL" if sc >= 0.90 else "WARNING",
                        message=f"{p1}/{p2} correlation: {sc:.0%}. Trading both = double exposure.",
                    ))
                elif sc <= self.ANTI_CORR_THRESHOLD:
                    alerts.append(CorrelationAlert(
                        pair1=p1, pair2=p2, correlation=sc,
                        alert_type="ANTI_CORR",
                        severity="WARNING",
                        message=f"{p1}/{p2} anti-correlated: {sc:.0%}. Long both = hedged position (low edge).",
                    ))

                # Regime shift
                if self._prev_corr is not None and p1 in self._prev_corr.index and p2 in self._prev_corr.columns:
                    pc = float(self._prev_corr.loc[p1, p2])
                    if abs(sc - pc) >= self.REGIME_SHIFT_DELTA:
                        alerts.append(CorrelationAlert(
                            pair1=p1, pair2=p2, correlation=sc,
                            alert_type="REGIME_SHIFT",
                            severity="WARNING",
                            message=f"Correlation regime shift: {p1}/{p2} moved from {pc:.0%} to {sc:.0%}.",
                        ))
        return alerts

    def _top_correlations(self, corr: pd.DataFrame, n: int = 5) -> List[Dict]:
        pairs = list(corr.columns); results = []
        for i in range(len(pairs)):
            for j in range(i+1, len(pairs)):
                p1, p2 = pairs[i], pairs[j]
                if p1 in corr.index and p2 in corr.columns:
                    results.append({"pair1": p1, "pair2": p2, "correlation": round(float(corr.loc[p1, p2]), 4)})
        return sorted(results, key=lambda x: abs(x["correlation"]), reverse=True)[:n]

    def _best_diversifiers(self, corr: pd.DataFrame, n: int = 5) -> List[Dict]:
        avg_abs = {p: float(corr[p].drop(p).abs().mean()) for p in corr.columns}
        return [
            {"pair": p, "avg_abs_correlation": round(v, 4), "diversification": "Excellent" if v < 0.3 else "Good"}
            for p, v in sorted(avg_abs.items(), key=lambda x: x[1])[:n]
        ]

    def _matrix_to_dict(self, corr: pd.DataFrame) -> Dict:
        return {
            row: {col: round(float(corr.loc[row, col]), 4) for col in corr.columns}
            for row in corr.index
        }
