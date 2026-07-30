# licensing/subscription_tiers.py
"""Quantoryx Subscription Tier System — 4 tiers, 30+ feature flags, FeatureGate checker."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum


class Tier(str, Enum):
    FREE="FREE"; PRO="PRO"; ELITE="ELITE"; PROP_FIRM="PROP_FIRM"


@dataclass
class TierConfig:
    name: str; tier: Tier; monthly_price_usd: float; annual_price_usd: float
    max_strategies: int; ml_signal_access: bool; regime_adaptive_access: bool
    max_pairs: int; live_signals: bool; signal_history_days: int
    consensus_engine_access: bool; confidence_scoring: bool
    portfolio_intelligence: bool; adaptive_sizing: bool; max_concurrent_strategies: int
    trade_journal_access: bool; journal_trade_limit: int; advanced_analytics: bool
    backtesting_access: bool; max_backtest_bars: int; walk_forward_access: bool
    paper_trading_access: bool; live_trading_access: bool; max_broker_connections: int
    telegram_alerts: bool; email_alerts: bool; discord_alerts: bool; max_alert_rules: int
    api_access: bool; api_rate_limit_per_min: int; webhook_support: bool
    prop_firm_mode: bool; genetic_optimizer: bool; black_swan_defense: bool
    marketplace_access: bool; marketplace_publish: bool; signal_mirror: bool
    mql_generator: bool; correlation_scanner: bool; ai_coach: bool; risk_rating: bool
    support_tier: str; white_label: bool = False


TIER_CONFIGS: Dict[Tier, TierConfig] = {
    Tier.FREE: TierConfig(
        name="Free", tier=Tier.FREE, monthly_price_usd=0, annual_price_usd=0,
        max_strategies=3, ml_signal_access=False, regime_adaptive_access=False,
        max_pairs=2, live_signals=False, signal_history_days=7,
        consensus_engine_access=False, confidence_scoring=False,
        portfolio_intelligence=False, adaptive_sizing=False, max_concurrent_strategies=1,
        trade_journal_access=True, journal_trade_limit=50, advanced_analytics=False,
        backtesting_access=True, max_backtest_bars=1000, walk_forward_access=False,
        paper_trading_access=False, live_trading_access=False, max_broker_connections=0,
        telegram_alerts=False, email_alerts=False, discord_alerts=False, max_alert_rules=2,
        api_access=False, api_rate_limit_per_min=0, webhook_support=False,
        prop_firm_mode=False, genetic_optimizer=False, black_swan_defense=False,
        marketplace_access=True, marketplace_publish=False, signal_mirror=False,
        mql_generator=False, correlation_scanner=False, ai_coach=False, risk_rating=False,
        support_tier="community",
    ),
    Tier.PRO: TierConfig(
        name="Pro", tier=Tier.PRO, monthly_price_usd=49, annual_price_usd=470,
        max_strategies=18, ml_signal_access=True, regime_adaptive_access=True,
        max_pairs=5, live_signals=True, signal_history_days=90,
        consensus_engine_access=True, confidence_scoring=True,
        portfolio_intelligence=False, adaptive_sizing=True, max_concurrent_strategies=3,
        trade_journal_access=True, journal_trade_limit=500, advanced_analytics=True,
        backtesting_access=True, max_backtest_bars=10000, walk_forward_access=True,
        paper_trading_access=True, live_trading_access=True, max_broker_connections=1,
        telegram_alerts=True, email_alerts=True, discord_alerts=True, max_alert_rules=20,
        api_access=False, api_rate_limit_per_min=0, webhook_support=False,
        prop_firm_mode=True, genetic_optimizer=False, black_swan_defense=True,
        marketplace_access=True, marketplace_publish=True, signal_mirror=False,
        mql_generator=True, correlation_scanner=True, ai_coach=False, risk_rating=True,
        support_tier="email",
    ),
    Tier.ELITE: TierConfig(
        name="Elite", tier=Tier.ELITE, monthly_price_usd=149, annual_price_usd=1430,
        max_strategies=18, ml_signal_access=True, regime_adaptive_access=True,
        max_pairs=20, live_signals=True, signal_history_days=365,
        consensus_engine_access=True, confidence_scoring=True,
        portfolio_intelligence=True, adaptive_sizing=True, max_concurrent_strategies=10,
        trade_journal_access=True, journal_trade_limit=0, advanced_analytics=True,
        backtesting_access=True, max_backtest_bars=100000, walk_forward_access=True,
        paper_trading_access=True, live_trading_access=True, max_broker_connections=3,
        telegram_alerts=True, email_alerts=True, discord_alerts=True, max_alert_rules=100,
        api_access=True, api_rate_limit_per_min=60, webhook_support=True,
        prop_firm_mode=True, genetic_optimizer=True, black_swan_defense=True,
        marketplace_access=True, marketplace_publish=True, signal_mirror=True,
        mql_generator=True, correlation_scanner=True, ai_coach=True, risk_rating=True,
        support_tier="priority",
    ),
    Tier.PROP_FIRM: TierConfig(
        name="Prop Firm / Institutional", tier=Tier.PROP_FIRM,
        monthly_price_usd=499, annual_price_usd=4790,
        max_strategies=18, ml_signal_access=True, regime_adaptive_access=True,
        max_pairs=100, live_signals=True, signal_history_days=0,
        consensus_engine_access=True, confidence_scoring=True,
        portfolio_intelligence=True, adaptive_sizing=True, max_concurrent_strategies=0,
        trade_journal_access=True, journal_trade_limit=0, advanced_analytics=True,
        backtesting_access=True, max_backtest_bars=0, walk_forward_access=True,
        paper_trading_access=True, live_trading_access=True, max_broker_connections=0,
        telegram_alerts=True, email_alerts=True, discord_alerts=True, max_alert_rules=0,
        api_access=True, api_rate_limit_per_min=600, webhook_support=True,
        prop_firm_mode=True, genetic_optimizer=True, black_swan_defense=True,
        marketplace_access=True, marketplace_publish=True, signal_mirror=True,
        mql_generator=True, correlation_scanner=True, ai_coach=True, risk_rating=True,
        support_tier="dedicated", white_label=True,
    ),
}


class FeatureGate:
    @staticmethod
    def get_config(tier: str) -> TierConfig:
        try: return TIER_CONFIGS[Tier(tier.upper())]
        except: return TIER_CONFIGS[Tier.FREE]

    @staticmethod
    def check(tier: str, feature: str) -> bool:
        val = getattr(FeatureGate.get_config(tier), feature, None)
        if val is None: return False
        if isinstance(val, bool): return val
        if isinstance(val, int): return val != 0
        return bool(val)

    @staticmethod
    def require(tier: str, feature: str, label: Optional[str] = None):
        if not FeatureGate.check(tier, feature):
            name = label or feature.replace("_"," ").title()
            raise PermissionError(f"Your plan ({tier}) does not include {name}. Upgrade to unlock.")

    @staticmethod
    def get_limits(tier: str) -> Dict[str, Any]:
        c = FeatureGate.get_config(tier)
        return {f: getattr(c, f) for f in c.__dataclass_fields__}

    @staticmethod
    def compare_all_tiers() -> List[Dict]:
        return [FeatureGate.get_limits(t.value) for t in Tier]
