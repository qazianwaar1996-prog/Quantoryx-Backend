# mirror/signal_mirror.py
"""
Quantoryx Multi-Account Signal Mirror.

One master account generates signals.
N slave accounts copy them instantly with custom lot sizing.

Use case: Prop traders running 5 funded accounts ($100K each)
can manage all 500K from a single Quantoryx dashboard.

Features:
  - Master → Slave signal propagation
  - Per-slave lot size multiplier (0.01× to 10×)
  - Per-slave pair filter (slave only copies certain pairs)
  - Per-slave strategy filter (slave only copies certain strategies)
  - Reverse mode (slave takes opposite signals — for hedging)
  - Delay mode (slave copies with N-second delay)
  - Kill switch per slave (pause without disconnecting)
  - Full copy log with attribution
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable
import asyncio
from utils.logging_config import get_logger

logger = get_logger("mirror.signal_mirror")


@dataclass
class SlaveAccount:
    """Configuration for a single slave account in the mirror network."""
    slave_id: str
    name: str                         # friendly name e.g. "FTMO Account 1"
    broker: str                       # "mt4", "mt5", "oanda", "paper"
    account_number: str
    lot_multiplier: float = 1.0       # scale lots from master
    allowed_pairs: List[str] = field(default_factory=list)    # [] = all
    allowed_strategies: List[str] = field(default_factory=list)  # [] = all
    is_active: bool = True
    is_reversed: bool = False         # copy opposite direction
    delay_seconds: int = 0            # signal copy delay
    max_lot_size: float = 10.0        # absolute cap
    copy_sl: bool = True              # copy stop loss
    copy_tp: bool = True              # copy take profit
    notes: str = ""


@dataclass
class MirrorSignal:
    """A signal propagated from master to slaves."""
    signal_id: str
    master_signal: int               # 1=BUY, -1=SELL
    pair: str
    strategy: str
    entry_price: float
    stop_loss: float
    take_profit: float
    master_lot_size: float
    confidence: float
    timestamp: str
    propagated_to: List[str] = field(default_factory=list)   # slave IDs
    slave_results: Dict[str, Dict] = field(default_factory=dict)


class SignalMirrorEngine:
    """
    Manages master→slave signal mirroring across multiple accounts.

    In production, each slave would connect to its broker API.
    Here, the engine provides the routing, filtering, and logging
    layer that sits on top of broker execution adapters.

    Usage:
        mirror = SignalMirrorEngine(master_id="user_123")
        mirror.add_slave(SlaveAccount(slave_id="s1", name="FTMO #1", ...))
        await mirror.propagate_signal(signal)
    """

    def __init__(self, master_id: str, execution_fn: Optional[Callable] = None):
        self.master_id    = master_id
        self._slaves: Dict[str, SlaveAccount] = {}
        self._signal_log: List[MirrorSignal] = []
        self._execution_fn = execution_fn   # async fn(slave, signal) → result

    # ── Slave Management ─────────────────────────────────────────────────────

    def add_slave(self, slave: SlaveAccount) -> Dict:
        self._slaves[slave.slave_id] = slave
        logger.info("Slave added: %s (%s %s)", slave.name, slave.broker, slave.account_number)
        return {"added": True, "slave_id": slave.slave_id, "name": slave.name}

    def remove_slave(self, slave_id: str) -> Dict:
        if slave_id in self._slaves:
            del self._slaves[slave_id]
        return {"removed": True, "slave_id": slave_id}

    def toggle_slave(self, slave_id: str, active: bool) -> Dict:
        if slave_id in self._slaves:
            self._slaves[slave_id].is_active = active
        return {"slave_id": slave_id, "is_active": active}

    def update_slave(self, slave_id: str, updates: Dict) -> Dict:
        if slave_id not in self._slaves:
            raise ValueError(f"Slave {slave_id} not found.")
        slave = self._slaves[slave_id]
        for k, v in updates.items():
            if hasattr(slave, k):
                setattr(slave, k, v)
        return {"updated": True, "slave_id": slave_id}

    def list_slaves(self) -> List[Dict]:
        return [self._slave_to_dict(s) for s in self._slaves.values()]

    # ── Signal Propagation ────────────────────────────────────────────────────

    async def propagate_signal(
        self,
        signal: int,
        pair: str,
        strategy: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        master_lot: float,
        confidence: float = 0.5,
    ) -> MirrorSignal:
        """
        Propagate a master signal to all eligible slave accounts.
        Filters are applied per slave before execution.
        """
        import uuid
        ms = MirrorSignal(
            signal_id=str(uuid.uuid4())[:8],
            master_signal=signal,
            pair=pair,
            strategy=strategy,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            master_lot_size=master_lot,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        active_slaves = [s for s in self._slaves.values() if s.is_active]
        tasks = []
        for slave in active_slaves:
            if self._should_copy(slave, pair, strategy):
                tasks.append(self._copy_to_slave(slave, ms))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for slave, result in zip(active_slaves, results):
                if isinstance(result, Exception):
                    ms.slave_results[slave.slave_id] = {"error": str(result)}
                else:
                    ms.slave_results[slave.slave_id] = result
                    ms.propagated_to.append(slave.slave_id)

        self._signal_log.append(ms)
        logger.info("Signal %s propagated to %d/%d slaves",
                    ms.signal_id, len(ms.propagated_to), len(active_slaves))
        return ms

    async def _copy_to_slave(self, slave: SlaveAccount, ms: MirrorSignal) -> Dict:
        """Apply slave-specific transforms and execute the copied signal."""
        if slave.delay_seconds > 0:
            await asyncio.sleep(slave.delay_seconds)

        # Compute slave lot
        slave_lot = min(
            ms.master_lot_size * slave.lot_multiplier,
            slave.max_lot_size,
        )

        # Reverse signal if configured
        direction = -ms.master_signal if slave.is_reversed else ms.master_signal

        # SL/TP pass-through
        sl = ms.stop_loss  if slave.copy_sl else None
        tp = ms.take_profit if slave.copy_tp else None

        if self._execution_fn:
            result = await self._execution_fn(slave, {
                "signal": direction, "pair": ms.pair, "lot": slave_lot,
                "entry": ms.entry_price, "sl": sl, "tp": tp,
            })
        else:
            # Simulation mode (no live broker)
            result = {
                "executed": True, "mode": "simulation",
                "slave_id": slave.slave_id, "direction": direction,
                "lot": round(slave_lot, 4),
                "pair": ms.pair, "entry": ms.entry_price,
            }

        return result

    def _should_copy(self, slave: SlaveAccount, pair: str, strategy: str) -> bool:
        """Check if this slave should copy this signal."""
        if slave.allowed_pairs and pair not in slave.allowed_pairs:
            return False
        if slave.allowed_strategies and strategy not in slave.allowed_strategies:
            return False
        return True

    # ── Reporting ─────────────────────────────────────────────────────────────

    def get_mirror_log(self, limit: int = 50) -> List[Dict]:
        return [
            {
                "signal_id":      s.signal_id,
                "pair":           s.pair,
                "strategy":       s.strategy,
                "direction":      {1:"BUY",-1:"SELL",0:"HOLD"}.get(s.master_signal,"HOLD"),
                "confidence":     s.confidence,
                "timestamp":      s.timestamp,
                "slaves_copied":  len(s.propagated_to),
                "slave_results":  s.slave_results,
            }
            for s in reversed(self._signal_log[-limit:])
        ]

    def get_mirror_stats(self) -> Dict:
        total = len(self._signal_log)
        return {
            "master_id":       self.master_id,
            "total_slaves":    len(self._slaves),
            "active_slaves":   sum(1 for s in self._slaves.values() if s.is_active),
            "total_signals":   total,
            "avg_propagation": round(
                sum(len(s.propagated_to) for s in self._signal_log) / total if total > 0 else 0, 2
            ),
        }

    def _slave_to_dict(self, s: SlaveAccount) -> Dict:
        return {
            "slave_id": s.slave_id, "name": s.name, "broker": s.broker,
            "account_number": s.account_number, "lot_multiplier": s.lot_multiplier,
            "allowed_pairs": s.allowed_pairs, "allowed_strategies": s.allowed_strategies,
            "is_active": s.is_active, "is_reversed": s.is_reversed,
            "delay_seconds": s.delay_seconds, "max_lot_size": s.max_lot_size,
        }
