import json
import logging
from pathlib import Path

from models import Listing

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "seen_listings.json"
PAGINATION_STATE_FILE = Path(__file__).parent / "pagination_state.json"


def load_seen_ids() -> set[str]:
    """Load previously seen listing IDs from disk."""
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("Failed to load seen listings: %s", e)
        return set()


def save_seen_ids(ids: set[str]) -> None:
    """Persist seen listing IDs to disk."""
    STATE_FILE.write_text(json.dumps(sorted(ids), ensure_ascii=False), encoding="utf-8")


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
        seen.update(l.id for l in new_listings)
        save_seen_ids(seen)
        logger.info("Found %d new listings (%d total seen)", len(new_listings), len(seen))
    else:
        logger.info("No new listings (tracking %d seen)", len(seen))
    return new_listings
