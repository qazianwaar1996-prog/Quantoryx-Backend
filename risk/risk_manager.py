# risk/risk_manager.py

from typing import Dict, Any, Tuple, Optional


class RiskManager:
    """
    Manages risk on an individual trade level and account level.
    Enforces drawdown limits, concurrent open trade restrictions, and exposure ceilings.
    """
    def __init__(
        self,
        risk_per_trade_pct: float = 1.0,        # Risk 1.0% of balance per trade
        max_daily_loss_pct: float = 3.0,        # Pause trading if daily loss reaches 3.0%
        max_total_drawdown_pct: float = 10.0,   # Pause trading if peak-to-trough drawdown reaches 10.0%
        max_concurrent_trades: int = 3,         # Maximum open trades at any time
        max_exposure_per_pair_pct: float = 5.0, # Maximum allocation risk per single pair/symbol
        default_rr_ratio: float = 2.0,          # Default Risk-to-Reward ratio (e.g. 1:2)
    ):
        self.risk_per_trade_pct = risk_per_trade_pct / 100.0
        self.max_daily_loss_pct = max_daily_loss_pct / 100.0
        self.max_total_drawdown_pct = max_total_drawdown_pct / 100.0
        self.max_concurrent_trades = max_concurrent_trades
        self.max_exposure_per_pair_pct = max_exposure_per_pair_pct / 100.0
        self.default_rr_ratio = default_rr_ratio

        # State tracking (updated dynamically by backtester/portfolio manager)
        self.active_trades_count = 0
        self.pair_allocations: Dict[str, float] = {}  # symbol -> allocated size in money
        self.daily_accumulated_loss = 0.0
        self.account_drawdown_pct = 0.0

    def calculate_position_size(
        self,
        balance: float,
        entry_price: float,
        stop_loss_price: float
    ) -> float:
        """
        Calculates the trade position size (units) dynamically based on 
        the maximum risk percent of the current account balance and stop loss distance.
        Formula: Size = (Balance * Risk%) / (Entry Price - Stop Loss Price)
        """
        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            return 0.0

        risk_amount = balance * self.risk_per_trade_pct
        position_size = risk_amount / sl_distance
        return round(position_size, 4)

    def evaluate_entry_allowance(
        self,
        symbol: str,
        balance: float,
        current_drawdown_pct: float,
        daily_loss_amount: float,
        proposed_notional_size: float
    ) -> Tuple[bool, str]:
        """
        Validates account-level risk rules before allowing an entry signal to execute.
        """
        # 1. Check Max Total Drawdown Limit
        if current_drawdown_pct >= self.max_total_drawdown_pct:
            return False, "REJECTED: Maximum total drawdown limit reached."

        # 2. Check Daily Drawdown Limit
        daily_loss_pct = daily_loss_amount / balance if balance > 0 else 0.0
        if daily_loss_pct >= self.max_daily_loss_pct:
            return False, "REJECTED: Daily maximum loss threshold breached."

        # 3. Check Max Concurrent Open Trades
        if self.active_trades_count >= self.max_concurrent_trades:
            return False, "REJECTED: Max concurrent trade limit reached."

        # 4. Check Single-Pair Exposure Limits
        current_pair_exposure = self.pair_allocations.get(symbol, 0.0)
        total_proposed_exposure = current_pair_exposure + proposed_notional_size
        max_allowed_pair_exposure = balance * self.max_exposure_per_pair_pct

        if total_proposed_exposure > max_allowed_pair_exposure:
            return False, f"REJECTED: Exceeds maximum exposure limit of {self.max_exposure_per_pair_pct * 100}% per pair."

        return True, "APPROVED"

    def calculate_sl_tp(
        self,
        direction: str,
        entry_price: float,
        stop_loss_pct: float,
        rr_ratio: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        Generates Stop Loss (SL) and Take Profit (TP) target prices.
        If rr_ratio is not specified, uses the configured default ratio.
        """
        rr = rr_ratio if rr_ratio is not None else self.default_rr_ratio
        
        if direction.upper() in ["LONG", "BUY", "1"]:
            sl_price = entry_price * (1.0 - (stop_loss_pct / 100.0))
            sl_distance = entry_price - sl_price
            tp_price = entry_price + (sl_distance * rr)
        else:  # SHORT
            sl_price = entry_price * (1.0 + (stop_loss_pct / 100.0))
            sl_distance = sl_price - entry_price
            tp_price = entry_price - (sl_distance * rr)

        return round(sl_price, 5), round(tp_price, 5)

    def register_trade_open(self, symbol: str, notional_size: float):
        """
        Tracks trade metrics when an entry is approved and initiated.
        """
        self.active_trades_count += 1
        self.pair_allocations[symbol] = self.pair_allocations.get(symbol, 0.0) + notional_size

    def register_trade_close(self, symbol: str, notional_size: float, realized_pnl: float):
        """
        Resets and updates metrics when a trade completes.
        """
        self.active_trades_count = max(0, self.active_trades_count - 1)
        self.pair_allocations[symbol] = max(0.0, self.pair_allocations.get(symbol, 0.0) - notional_size)
        
        if realized_pnl < 0:
            self.daily_accumulated_loss += abs(realized_pnl)

    def reset_daily_limits(self):
        """
        Resets the intraday loss tracking counter. Called at daily market close.
        """
        self.daily_accumulated_loss = 0.0
