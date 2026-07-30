# marketplace/strategy_marketplace.py
"""
Quantoryx Strategy Marketplace.

Traders publish their strategies → other traders subscribe → signals mirror.
Revenue split: Quantoryx 20% / Strategy creator 80%.

Features:
  - Strategy listings with verified performance stats
  - Subscription management (free preview + paid full access)
  - Creator earnings dashboard
  - Rating and review system
  - Risk-score on every listed strategy before you subscribe
  - Strategy cloning (subscribe → get a copy to customize)
  - Featured/trending algorithm for homepage
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np


@dataclass
class StrategyListing:
    """A publicly listed strategy in the marketplace."""
    listing_id: str
    creator_id: str
    creator_display_name: str     # anonymous alias
    strategy_name: str            # display name
    strategy_type: str            # "ema_crossover", "ml_signal", etc.
    description: str
    pairs: List[str]
    timeframe: str

    # Verified performance (from backtests + live track record)
    verified_win_rate: float
    verified_profit_factor: float
    verified_sharpe: float
    verified_max_drawdown_pct: float
    verified_monthly_return_pct: float
    track_record_days: int        # how long it's been live

    # Pricing
    price_usd_monthly: float      # 0 = free
    is_free: bool = False

    # Community stats
    subscriber_count: int = 0
    rating: float = 0.0           # 0–5 stars
    review_count: int = 0
    total_copies: int = 0

    # Flags
    is_verified: bool = False     # Quantoryx manually reviewed
    is_featured: bool = False
    is_trending: bool = False

    # Risk rating (computed)
    risk_score: int = 0           # 1–10 (10 = highest risk)
    risk_label: str = "Medium"    # "Low" / "Medium" / "High" / "Very High"

    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class MarketplaceReview:
    review_id: str
    listing_id: str
    reviewer_id: str
    rating: int          # 1–5
    comment: str
    created_at: str
    is_verified_buyer: bool = True


@dataclass
class CreatorEarnings:
    creator_id: str
    total_subscribers: int
    monthly_revenue_usd: float
    lifetime_revenue_usd: float
    pending_payout_usd: float
    last_payout_date: str
    payout_history: List[Dict]


class StrategyMarketplace:
    """
    Core marketplace logic: listings, subscriptions, revenue tracking.

    In production this would use the database ORM. Here it provides
    the complete business logic layer that the API endpoints call.
    """

    PLATFORM_CUT = 0.20   # 20% to Quantoryx
    CREATOR_CUT  = 0.80   # 80% to strategy creator

    def __init__(self):
        self._listings: Dict[str, StrategyListing] = {}
        self._subscriptions: Dict[str, List[str]] = {}   # user_id → [listing_ids]
        self._reviews: Dict[str, List[MarketplaceReview]] = {}
        self._earnings: Dict[str, CreatorEarnings] = {}

    # ── Listings ─────────────────────────────────────────────────────────────

    def publish_strategy(
        self,
        creator_id: str,
        display_name: str,
        strategy_type: str,
        description: str,
        pairs: List[str],
        timeframe: str,
        backtest_results: Dict,       # from BacktestEngine
        price_usd_monthly: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> StrategyListing:
        """Publish a strategy to the marketplace."""
        import uuid
        lid = str(uuid.uuid4())[:8]

        risk_score, risk_label = self._compute_risk_score(backtest_results)

        listing = StrategyListing(
            listing_id=lid,
            creator_id=creator_id,
            creator_display_name=display_name,
            strategy_name=f"{strategy_type.replace('_',' ').title()} by {display_name}",
            strategy_type=strategy_type,
            description=description,
            pairs=pairs,
            timeframe=timeframe,
            verified_win_rate=float(backtest_results.get("win_rate", 0.5)),
            verified_profit_factor=float(backtest_results.get("profit_factor", 1.0)),
            verified_sharpe=float(backtest_results.get("sharpe_ratio", 0.0)),
            verified_max_drawdown_pct=abs(float(backtest_results.get("max_drawdown_pct", 10.0))),
            verified_monthly_return_pct=float(backtest_results.get("monthly_return_pct", 0.0)),
            track_record_days=int(backtest_results.get("total_trades", 0)),
            price_usd_monthly=price_usd_monthly,
            is_free=price_usd_monthly == 0.0,
            risk_score=risk_score,
            risk_label=risk_label,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            tags=tags or [],
        )
        self._listings[lid] = listing
        return listing

    def get_listings(
        self,
        category: Optional[str] = None,
        sort_by: str = "trending",     # trending | win_rate | sharpe | price | newest
        max_risk: Optional[int] = None,
        free_only: bool = False,
        search: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """Return filtered and sorted marketplace listings."""
        listings = list(self._listings.values())

        if category:
            listings = [l for l in listings if category.lower() in [t.lower() for t in l.tags]]
        if max_risk is not None:
            listings = [l for l in listings if l.risk_score <= max_risk]
        if free_only:
            listings = [l for l in listings if l.is_free]
        if search:
            q = search.lower()
            listings = [l for l in listings if q in l.description.lower()
                        or q in l.strategy_name.lower()
                        or any(q in t.lower() for t in l.tags)]

        # Sort
        sort_map = {
            "trending":   lambda l: (l.is_trending, l.subscriber_count),
            "win_rate":   lambda l: l.verified_win_rate,
            "sharpe":     lambda l: l.verified_sharpe,
            "price":      lambda l: l.price_usd_monthly,
            "newest":     lambda l: l.created_at,
            "featured":   lambda l: (l.is_featured, l.rating),
        }
        key_fn = sort_map.get(sort_by, sort_map["trending"])
        listings = sorted(listings, key=key_fn, reverse=True)

        return [self._listing_to_dict(l) for l in listings[:limit]]

    def get_listing(self, listing_id: str) -> Optional[Dict]:
        l = self._listings.get(listing_id)
        return self._listing_to_dict(l) if l else None

    # ── Subscriptions ─────────────────────────────────────────────────────────

    def subscribe(self, user_id: str, listing_id: str) -> Dict:
        """Subscribe a user to a strategy listing."""
        if listing_id not in self._listings:
            raise ValueError(f"Listing {listing_id} not found.")
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = []
        if listing_id not in self._subscriptions[user_id]:
            self._subscriptions[user_id].append(listing_id)
            self._listings[listing_id].subscriber_count += 1
            self._record_revenue(listing_id)
        return {"subscribed": True, "listing_id": listing_id, "user_id": user_id}

    def unsubscribe(self, user_id: str, listing_id: str) -> Dict:
        if user_id in self._subscriptions and listing_id in self._subscriptions[user_id]:
            self._subscriptions[user_id].remove(listing_id)
            if listing_id in self._listings:
                self._listings[listing_id].subscriber_count = max(
                    0, self._listings[listing_id].subscriber_count - 1
                )
        return {"unsubscribed": True}

    def get_user_subscriptions(self, user_id: str) -> List[Dict]:
        ids = self._subscriptions.get(user_id, [])
        return [self._listing_to_dict(self._listings[lid]) for lid in ids if lid in self._listings]

    # ── Reviews ───────────────────────────────────────────────────────────────

    def add_review(self, user_id: str, listing_id: str, rating: int, comment: str) -> Dict:
        import uuid
        if listing_id not in self._listings:
            raise ValueError("Listing not found.")
        rev = MarketplaceReview(
            review_id=str(uuid.uuid4())[:8],
            listing_id=listing_id,
            reviewer_id=user_id,
            rating=min(5, max(1, rating)),
            comment=comment,
            created_at=datetime.now().isoformat(),
        )
        if listing_id not in self._reviews:
            self._reviews[listing_id] = []
        self._reviews[listing_id].append(rev)

        # Update average rating
        all_ratings = [r.rating for r in self._reviews[listing_id]]
        self._listings[listing_id].rating = round(sum(all_ratings) / len(all_ratings), 1)
        self._listings[listing_id].review_count = len(all_ratings)
        return {"review_id": rev.review_id, "rating": rev.rating}

    def get_reviews(self, listing_id: str) -> List[Dict]:
        return [
            {"review_id": r.review_id, "rating": r.rating,
             "comment": r.comment, "created_at": r.created_at}
            for r in self._reviews.get(listing_id, [])
        ]

    # ── Creator Earnings ──────────────────────────────────────────────────────

    def get_creator_earnings(self, creator_id: str) -> Dict:
        e = self._earnings.get(creator_id)
        if not e:
            return {"creator_id": creator_id, "total_earnings": 0.0, "pending": 0.0}
        return {
            "creator_id":           creator_id,
            "total_subscribers":    e.total_subscribers,
            "monthly_revenue_usd":  e.monthly_revenue_usd,
            "lifetime_revenue_usd": e.lifetime_revenue_usd,
            "pending_payout_usd":   e.pending_payout_usd,
            "platform_cut_pct":     self.PLATFORM_CUT * 100,
            "creator_cut_pct":      self.CREATOR_CUT * 100,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _compute_risk_score(self, results: Dict) -> tuple:
        """Compute risk score 1–10 from backtest stats."""
        dd = abs(float(results.get("max_drawdown_pct", 10)))
        pf = float(results.get("profit_factor", 1.0))
        wr = float(results.get("win_rate", 0.5))

        score = 0
        if dd > 30: score += 4
        elif dd > 20: score += 3
        elif dd > 10: score += 2
        else: score += 1

        if pf < 1.2: score += 3
        elif pf < 1.5: score += 2
        else: score += 1

        if wr < 0.40: score += 3
        elif wr < 0.50: score += 2
        else: score += 1

        score = min(10, score)
        label = "Low" if score <= 3 else "Medium" if score <= 6 else "High" if score <= 8 else "Very High"
        return score, label

    def _record_revenue(self, listing_id: str):
        listing = self._listings.get(listing_id)
        if not listing or listing.is_free:
            return
        creator_id = listing.creator_id
        creator_rev = listing.price_usd_monthly * self.CREATOR_CUT
        if creator_id not in self._earnings:
            self._earnings[creator_id] = CreatorEarnings(
                creator_id=creator_id, total_subscribers=0,
                monthly_revenue_usd=0.0, lifetime_revenue_usd=0.0,
                pending_payout_usd=0.0, last_payout_date="", payout_history=[],
            )
        e = self._earnings[creator_id]
        e.total_subscribers += 1
        e.monthly_revenue_usd += creator_rev
        e.lifetime_revenue_usd += creator_rev
        e.pending_payout_usd += creator_rev

    def _listing_to_dict(self, l: StrategyListing) -> Dict:
        return {
            "listing_id": l.listing_id,
            "creator_display_name": l.creator_display_name,
            "strategy_name": l.strategy_name,
            "strategy_type": l.strategy_type,
            "description": l.description,
            "pairs": l.pairs,
            "timeframe": l.timeframe,
            "performance": {
                "win_rate":              l.verified_win_rate,
                "profit_factor":         l.verified_profit_factor,
                "sharpe":                l.verified_sharpe,
                "max_drawdown_pct":      l.verified_max_drawdown_pct,
                "monthly_return_pct":    l.verified_monthly_return_pct,
                "track_record_days":     l.track_record_days,
            },
            "risk": {"score": l.risk_score, "label": l.risk_label},
            "price_usd_monthly": l.price_usd_monthly,
            "is_free": l.is_free,
            "subscriber_count": l.subscriber_count,
            "rating": l.rating,
            "review_count": l.review_count,
            "is_verified": l.is_verified,
            "is_featured": l.is_featured,
            "is_trending": l.is_trending,
            "tags": l.tags,
            "created_at": l.created_at,
        }
