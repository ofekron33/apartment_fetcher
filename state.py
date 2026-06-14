import json
import logging
from datetime import date, timedelta
from pathlib import Path

from models import Listing

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "seen_listings.json"
PAGINATION_STATE_FILE = Path(__file__).parent / "pagination_state.json"

DEFAULT_MAX_AGE_DAYS = 30


def prune_expired(seen: dict[str, str], max_age_days: int) -> dict[str, str]:
    """Remove entries older than max_age_days from the seen dict."""
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    before = len(seen)
    pruned = {id_: first_seen for id_, first_seen in seen.items() if first_seen >= cutoff}
    removed = before - len(pruned)
    if removed:
        logger.info("Pruned %d expired entries from seen state (older than %d days)", removed, max_age_days)
    return pruned


def load_seen_ids(max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> dict[str, str]:
    """Load previously seen listing IDs from disk as {id: first_seen_date}.

    Backward-compatible: if the file contains a list, converts to dict with today's date.
    Auto-prunes entries older than max_age_days.
    """
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("Failed to load seen listings: %s", e)
        return {}
    # Backward compatibility: convert list format to dict
    if isinstance(data, list):
        today = date.today().isoformat()
        data = {str(id_): today for id_ in data}
        logger.info("Migrated seen_listings.json from list to dict format (%d entries)", len(data))
    return prune_expired(data, max_age_days)


def save_seen_ids(ids: dict[str, str]) -> None:
    """Persist seen listing IDs to disk as {id: first_seen_date}."""
    STATE_FILE.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")


def load_resume_page() -> int:
    """Load the deepest page we've fully scraped. Returns 0 if no state."""
    if not PAGINATION_STATE_FILE.exists():
        return 0
    try:
        data = json.loads(PAGINATION_STATE_FILE.read_text(encoding="utf-8"))
        return data.get("resume_page", 0)
    except (json.JSONDecodeError, TypeError):
        return 0


def save_resume_page(page: int) -> None:
    """Save the deepest page we've fully scraped."""
    PAGINATION_STATE_FILE.write_text(json.dumps({"resume_page": page}), encoding="utf-8")
    logger.debug("Saved resume_page=%d", page)


def filter_new(listings: list[Listing]) -> list[Listing]:
    """Return only listings we haven't seen before, and mark them as seen."""
    seen = load_seen_ids()
    new_listings = [l for l in listings if l.id not in seen]
    if new_listings:
        today = date.today().isoformat()
        for l in new_listings:
            seen[l.id] = today
        save_seen_ids(seen)
        logger.info("Found %d new listings (%d total seen)", len(new_listings), len(seen))
    else:
        logger.info("No new listings (tracking %d seen)", len(seen))
    return new_listings
