# ============================================================
# strategies/base.py — Abstract Base Strategy
# ============================================================
"""
Common contract for every Quantoryx trading strategy.

Design notes
------------
* Strategies are **self-contained signal generators**. They read OHLC data
  and emit a discrete ``signal`` column (1 = long, -1 = short, 0 = flat).
* Default parameters are sourced from :data:`config.STRATEGY_DEFAULTS`
  keyed by :attr:`BaseStrategy.CONFIG_KEY`, so any parameter omitted by the
  caller (e.g. a partial CLI override) falls back to a sane default.
* Strategies are **column-case agnostic**: they accept ``Close``/``close``
  interchangeably via :meth:`_series`, because the backtest engine may feed
  either Title-case or lower-case frames.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import pandas as pd


class BaseStrategy(ABC):
    """Abstract base class shared by all strategies.

    Subclasses must define :attr:`CONFIG_KEY`, :attr:`name`,
    :meth:`prepare`, and :meth:`generate_signals`.
    """

    #: Key into ``config.STRATEGY_DEFAULTS`` for this strategy's defaults.
    CONFIG_KEY: str = ""

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        # Store only explicitly-provided params; defaults are merged lazily.
        self.params: Dict[str, Any] = dict(params or {})

    # ------------------------------------------------------------------
    # Contract
    # ------------------------------------------------------------------
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique, lower-case strategy identifier string."""
        ...

    @abstractmethod
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all required indicator columns to ``df`` and return it."""
        ...

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add a ``signal`` column (1 long / -1 short / 0 flat) and return ``df``."""
        ...

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def defaults(self) -> Dict[str, Any]:
        """Return this strategy's default parameter mapping from config."""
        # Imported lazily to avoid a circular import at module load time.
        from config import STRATEGY_DEFAULTS

        return dict(STRATEGY_DEFAULTS.get(self.CONFIG_KEY, {}))

    def get_param(self, key: str, default: Any = None) -> Any:
        """Resolve a parameter: explicit override → config default → ``default``."""
        if key in self.params and self.params[key] is not None:
            return self.params[key]
        return self.defaults().get(key, default)

    @staticmethod
    def _series(df: pd.DataFrame, name: str) -> pd.Series:
        """Case-insensitive OHLCV column accessor (``close`` or ``Close``)."""
        if name in df.columns:
            return df[name]
        title = name.title()
        if title in df.columns:
            return df[title]
        lower = name.lower()
        if lower in df.columns:
            return df[lower]
        raise KeyError(f"Column '{name}' not found. Available: {list(df.columns)}")

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """Full pipeline: copy → prepare indicators → generate signals."""
        df = df.copy()
        df = self.prepare(df)
        df = self.generate_signals(df)
        # Guarantee the contract column exists even if a subclass short-circuits.
        if "signal" not in df.columns:
            df["signal"] = 0
        return df
