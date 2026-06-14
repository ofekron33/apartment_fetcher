import logging
from typing import Optional

from models import Listing, ScoredListing

logger = logging.getLogger(__name__)


def passes_hard_filters(listing: Listing, config: dict) -> bool:
    """Return False if the listing fails any hard filter (should be discarded)."""
    filters = config.get("filters", {})
    min_rooms = filters.get("min_rooms", 2.5)
    max_floor_no_elevator = filters.get("max_floor_without_elevator", 2)

    # Disqualify: price out of range
    min_price = filters.get("min_price")
    max_price = filters.get("max_price")
    if listing.price is not None:
        if min_price is not None and listing.price < min_price:
            logger.debug("Filtered %s: price %d < min %d", listing.id, listing.price, min_price)
            return False
        if max_price is not None and listing.price > max_price:
            logger.debug("Filtered %s: price %d > max %d", listing.id, listing.price, max_price)
            return False

    # Disqualify: too few rooms
    if listing.rooms is not None and listing.rooms < min_rooms:
        logger.debug("Filtered %s: rooms %.1f < %.1f", listing.id, listing.rooms, min_rooms)
        return False

    # Disqualify: high floor without elevator
    if (
        listing.floor is not None
        and listing.floor >= (max_floor_no_elevator + 1)
        and listing.elevator is not None
        and not listing.elevator
    ):
        logger.debug("Filtered %s: floor %d without elevator", listing.id, listing.floor)
        return False

    return True


def score_listing(listing: Listing, config: dict) -> ScoredListing:
    """Score a listing based on soft criteria. Returns ScoredListing with breakdown."""
    scoring = config.get("scoring", {})
    total = 0
    breakdown = {}

    # Parking bonus
    if listing.parking:
        pts = scoring.get("parking_points", 10)
        total += pts
        breakdown["Parking"] = pts

    # Low floor bonus
    low_floor_max = scoring.get("low_floor_max", 2)
    if listing.floor is not None and listing.floor <= low_floor_max:
        pts = scoring.get("low_floor_points", 5)
        total += pts
        breakdown["Low floor"] = pts

    # 3+ rooms bonus
    if listing.rooms is not None and listing.rooms >= 3:
        pts = scoring.get("three_plus_rooms_points", 5)
        total += pts
        breakdown["3+ rooms"] = pts

    # Price score: lower price = more points (linear interpolation)
    price_max_pts = scoring.get("price_points_max", 10)
    price_low = scoring.get("price_range_low", 3000)
    price_high = scoring.get("price_range_high", 7000)
    if listing.price is not None and price_high > price_low:
        if listing.price <= price_low:
            pts = price_max_pts
        elif listing.price >= price_high:
            pts = 0
        else:
            ratio = 1 - (listing.price - price_low) / (price_high - price_low)
            pts = int(ratio * price_max_pts)
        if pts > 0:
            total += pts
            breakdown["Price"] = pts

    return ScoredListing(listing=listing, score=total, breakdown=breakdown)


def filter_and_score(listings: list[Listing], config: dict) -> list[ScoredListing]:
    """Apply hard filters, score survivors, return sorted by score descending."""
    passed = [l for l in listings if passes_hard_filters(l, config)]
    logger.info("%d/%d listings passed hard filters", len(passed), len(listings))

    scored = [score_listing(l, config) for l in passed]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored
