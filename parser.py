import json
import logging
from pathlib import Path
from typing import Optional

from models import Listing, REFERENCE_LAT, REFERENCE_LON, haversine_km

logger = logging.getLogger(__name__)

# Yad2 splits listings into categories under props.pageProps.feed.
# These are the listing-category keys to merge (skip metadata like "pagination").
FEED_CATEGORIES = ["private", "agency", "platinum", "yad1", "booster",
                    "kingOfTheHar", "trio", "leadingBroker", "lookalike"]

# Fallback: flat list paths from older site versions.
FLAT_FEED_PATHS = [
    ["props", "pageProps", "feedItems"],
    ["props", "pageProps", "feed", "feed_items"],
    ["data", "feed", "feed_items"],
]

# Tag names (Hebrew) that indicate features
TAG_PARKING = {"חניה", "חנייה", "parking"}
TAG_ELEVATOR = {"מעלית", "elevator"}

YAD2_ITEM_URL = "https://www.yad2.co.il/realestate/item/{}"


def _navigate(data: dict, path: list[str]) -> Optional[list]:
    """Navigate nested dict by key path, return value or None."""
    current = data
    for key in path:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current if isinstance(current, list) else None


def _extract_field(item: dict, candidates: list[str], default=None):
    """Try multiple field names, return first match."""
    for name in candidates:
        if name in item:
            return item[name]
        # Check nested structures like additionalDetails, metaData
        for nested_key in ("additionalDetails", "metaData", "row_4", "row_3"):
            nested = item.get(nested_key, {})
            if isinstance(nested, dict) and name in nested:
                return nested[name]
            if isinstance(nested, list):
                for entry in nested:
                    if isinstance(entry, dict) and entry.get("key") == name:
                        return entry.get("value")
    return default


def _parse_bool(value) -> Optional[bool]:
    """Parse various truthy/falsy representations."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1", "יש", "כן")
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _parse_number(value, as_float=False):
    """Parse a numeric value, stripping commas and currency symbols."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if as_float else int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("₪", "").replace("ש״ח", "").strip()
        try:
            return float(cleaned) if as_float else int(float(cleaned))
        except (ValueError, TypeError):
            return None
    return None


def find_feed_items(data: dict) -> Optional[list]:
    """Locate listing feed items — handles both category-split and flat formats."""
    # Primary: Yad2's current structure has categories under props.pageProps.feed
    feed = data
    for key in ["props", "pageProps", "feed"]:
        if isinstance(feed, dict) and key in feed:
            feed = feed[key]
        else:
            feed = None
            break

    if isinstance(feed, dict):
        merged = []
        for cat in FEED_CATEGORIES:
            items = feed.get(cat)
            if isinstance(items, list):
                merged.extend(items)
                logger.debug("Category '%s': %d items", cat, len(items))
            elif isinstance(items, dict):
                # yad1 might be a dict with nested items
                nested = items.get("items", items.get("feed_items", []))
                if isinstance(nested, list):
                    merged.extend(nested)
                    logger.debug("Category '%s' (nested): %d items", cat, len(nested))
        if merged:
            logger.info("Merged %d items from feed categories", len(merged))
            return merged

    # Fallback: flat list paths
    for path in FLAT_FEED_PATHS:
        items = _navigate(data, path)
        if items:
            logger.info("Found feed items at flat path: %s (%d items)", " -> ".join(path), len(items))
            return items

    logger.warning("Could not find feed items in any known structure")
    return None


def extract_pagination_info(data: dict) -> Optional[dict]:
    """Extract pagination metadata (total listings, total pages) from __NEXT_DATA__."""
    pag = _get_nested(data, "props", "pageProps", "feed", "pagination")
    if isinstance(pag, dict) and "total" in pag:
        return {"total": pag["total"], "total_pages": pag.get("totalPages")}
    return None


def _get_nested(d: dict, *keys, default=None):
    """Safely traverse nested dicts: _get_nested(d, "a", "b", "c") -> d["a"]["b"]["c"]."""
    current = d
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default
    return current


def _get_tags(item: dict) -> set[str]:
    """Extract tag names from the tags list."""
    tags = item.get("tags", [])
    if not isinstance(tags, list):
        return set()
    return {t.get("name", "").strip().lower() for t in tags if isinstance(t, dict)}


def parse_listing(item: dict) -> Optional[Listing]:
    """Parse a single raw JSON item into a Listing."""
    # ID
    listing_id = item.get("token") or item.get("id") or item.get("orderId")
    if listing_id is None:
        return None
    listing_id = str(listing_id)

    # Price (top-level)
    price = _parse_number(item.get("price"))

    # Rooms & size from additionalDetails
    details = item.get("additionalDetails", {})
    if not isinstance(details, dict):
        details = {}
    rooms = _parse_number(details.get("roomsCount"), as_float=True)
    size_sqm = _parse_number(details.get("squareMeter"))

    # Floor from address.house.floor
    floor = _parse_number(_get_nested(item, "address", "house", "floor"))

    # Address: street + house number
    street = _get_nested(item, "address", "street", "text", default="")
    house_num = _get_nested(item, "address", "house", "number")
    address = f"{street} {house_num}".strip() if street else ""

    # Neighborhood
    neighborhood = _get_nested(item, "address", "neighborhood", "text", default="")

    # Elevator and parking from tags
    tags = _get_tags(item)
    parking = any(t in tags for t in TAG_PARKING)
    elevator = any(t in tags for t in TAG_ELEVATOR)

    link = YAD2_ITEM_URL.format(listing_id)

    order_id = _parse_number(item.get("orderId"))

    # Coordinates and distance
    coords = _get_nested(item, "address", "coords")
    lat = None
    lon = None
    distance_km = None
    if isinstance(coords, dict):
        lat = coords.get("lat")
        lon = coords.get("lon")
        if lat is not None and lon is not None:
            distance_km = round(haversine_km(lat, lon, REFERENCE_LAT, REFERENCE_LON), 2)

    return Listing(
        id=listing_id,
        price=price,
        rooms=rooms,
        floor=floor,
        elevator=elevator,
        parking=parking,
        address=address,
        neighborhood=neighborhood,
        size_sqm=size_sqm,
        link=link,
        order_id=order_id,
        lat=lat,
        lon=lon,
        distance_km=distance_km,
    )


def parse_listings(data: dict, debug: bool = False) -> list[Listing]:
    """Parse all listings from __NEXT_DATA__ JSON.

    If debug=True, dumps raw feed items to debug_feed.json for field discovery.
    """
    feed_items = find_feed_items(data)
    if not feed_items:
        # In debug mode, dump the full structure keys to help discover the path
        if debug:
            debug_path = Path("debug_next_data_keys.json")
            _dump_structure(data, debug_path)
            logger.info("Dumped __NEXT_DATA__ key structure to %s", debug_path)
        return []

    if debug:
        debug_path = Path("debug_feed.json")
        # Dump first 3 items for field discovery
        sample = feed_items[:3]
        debug_path.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Dumped %d sample feed items to %s", len(sample), debug_path)

    listings = []
    for item in feed_items:
        if not isinstance(item, dict):
            continue
        # Skip promoted/ad items
        if item.get("type") == "ad" or item.get("isPromoted"):
            continue
        listing = parse_listing(item)
        if listing:
            listings.append(listing)

    logger.info("Parsed %d listings from %d feed items", len(listings), len(feed_items))
    return listings


def _dump_structure(data, path: Path, max_depth: int = 4):
    """Dump dict key structure (not values) for debugging."""

    def _keys(obj, depth=0):
        if depth >= max_depth:
            return f"<{type(obj).__name__}>"
        if isinstance(obj, dict):
            return {k: _keys(v, depth + 1) for k, v in obj.items()}
        if isinstance(obj, list):
            if obj:
                return [_keys(obj[0], depth + 1), f"... ({len(obj)} items)"]
            return []
        return f"<{type(obj).__name__}>"

    structure = _keys(data)
    path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")
