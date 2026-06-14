"""
Fetch apartments from 4kirot.com — pure API, no browser needed.
Uses the saved Firebase refresh token to authenticate.
Deduplicates listings across runs so only new ones are returned.

First-time setup: run setup_token.py once to save your token.
"""

import json
import logging
import sys
from pathlib import Path
import requests

from models import Listing, REFERENCE_LAT, REFERENCE_LON, haversine_km

sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger(__name__)

API_KEY = "AIzaSyASXIdOzl71__LJtYkSYS7kVzXorA9NDKg"
TOKEN_FILE = "firebase_token.json"
SEEN_FILE = Path(__file__).parent / "seen_4kirot.json"


def get_id_token():
    """Exchange the refresh token for a fresh Firebase ID token."""
    with open(TOKEN_FILE) as f:
        saved = json.load(f)

    resp = requests.post(
        f"https://securetoken.googleapis.com/v1/token?key={API_KEY}",
        data={
            "grant_type": "refresh_token",
            "refresh_token": saved["refresh_token"],
        },
        headers={"Referer": "https://4kirot.com/"},
    )

    if resp.status_code != 200:
        print(f"Token refresh failed: {resp.status_code} {resp.text[:300]}")
        return None

    data = resp.json()

    # Update saved refresh token (Google may rotate it)
    saved["refresh_token"] = data["refresh_token"]
    with open(TOKEN_FILE, "w") as f:
        json.dump(saved, f, indent=2)

    return data["id_token"]


def fetch_apartments(id_token):
    """Call the fetchapartments Cloud Function."""
    resp = requests.post(
        "https://us-central1-apartments-89793.cloudfunctions.net/fetchapartments",
        json={"data": None},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {id_token}",
        },
    )

    if resp.status_code == 200:
        data = resp.json()
        return data.get("result", {}).get("apartments", [])
    else:
        print(f"API error: {resp.status_code} {resp.text[:300]}")
        return None


def load_seen_ids() -> set[str]:
    """Load previously seen 4kirot listing IDs from disk."""
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        return set(data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("Failed to load seen 4kirot listings: %s", e)
        return set()


def save_seen_ids(ids: set[str]) -> None:
    """Persist seen 4kirot listing IDs to disk."""
    SEEN_FILE.write_text(json.dumps(sorted(ids), ensure_ascii=False), encoding="utf-8")


def filter_new(apartments: list[dict]) -> list[dict]:
    """Return only apartments we haven't seen before, and mark them as seen."""
    seen = load_seen_ids()
    new_apartments = [a for a in apartments if a["post_id"] not in seen]
    seen.update(a["post_id"] for a in apartments)
    save_seen_ids(seen)
    if new_apartments:
        logger.info("4kirot: %d new listings (%d total seen)", len(new_apartments), len(seen))
    else:
        logger.info("4kirot: no new listings (%d total seen)", len(seen))
    return new_apartments


# Cities to exclude from 4kirot results (only want Tel Aviv)
EXCLUDED_CITIES = [
    "רמת גן", "רמת-גן", "ר״ג", "ר\"ג", "ramat gan",
    "גבעתיים", "givatayim",
    "חולון", "holon",
    "בת ים", "bat yam",
    "הרצליה", "herzliya",
    "פתח תקווה", "petah tikva",
    "בני ברק", "bnei brak",
]


def _is_tel_aviv(address: str) -> bool:
    """Return True if the address appears to be in Tel Aviv (not another city)."""
    addr_lower = address.lower()
    return not any(city in addr_lower for city in EXCLUDED_CITIES)


def apartment_to_listing(apt: dict) -> Listing:
    """Convert a raw 4kirot apartment dict into a Listing object."""
    price = apt.get("price_parsed")
    if price is None:
        # Try parsing the string price
        raw = apt.get("price", "")
        if raw:
            try:
                price = int(float(str(raw).replace(",", "")))
            except (ValueError, TypeError):
                price = None

    date_str = apt.get("date")
    created_at = date_str if date_str else None

    lat = apt.get("lat")
    lon = apt.get("lng")
    distance_km = None
    if lat is not None and lon is not None:
        distance_km = round(haversine_km(lat, lon, REFERENCE_LAT, REFERENCE_LON), 2)

    return Listing(
        id=f"4k_{apt['post_id']}",
        source="4kirot",
        price=price,
        address=apt.get("address", ""),
        link="",
        facebook_url=apt.get("post_url"),
        is_realtor=apt.get("is_realtor"),
        author_name=apt.get("author_name"),
        created_at=created_at,
        lat=lat,
        lon=lon,
        distance_km=distance_km,
    )


def apartments_to_listings(apartments: list[dict]) -> list[Listing]:
    """Convert a list of raw 4kirot apartments into Listing objects, filtering to Tel Aviv only."""
    listings = []
    skipped = 0
    for apt in apartments:
        if not _is_tel_aviv(apt.get("address", "")):
            skipped += 1
            continue
        listings.append(apartment_to_listing(apt))
    if skipped:
        logger.info("4kirot: skipped %d non-Tel-Aviv listings", skipped)
    return listings


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("Getting fresh ID token...")
    id_token = get_id_token()
    if not id_token:
        print("Failed. Run setup_token.py to re-authenticate.")
        return

    print("Fetching apartments...")
    apartments = fetch_apartments(id_token)

    if apartments is None:
        print("Failed to fetch apartments.")
        return

    print(f"Got {len(apartments)} apartments from API")

    new_apartments = filter_new(apartments)
    print(f"New listings: {len(new_apartments)}")

    if not new_apartments:
        print("No new apartments since last run.")
        return

    with open("apartments.json", "w", encoding="utf-8") as f:
        json.dump(new_apartments, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(new_apartments)} new apartments to apartments.json")

    print("\nNew listings:")
    for apt in new_apartments[:10]:
        price = apt.get("price_parsed") or "N/A"
        addr = apt.get("address", "Unknown")
        realtor = " [Realtor]" if apt.get("is_realtor") else ""
        print(f"  {addr} - {price} ILS ({apt['author_name']}){realtor}")
    if len(new_apartments) > 10:
        print(f"  ... and {len(new_apartments) - 10} more")


if __name__ == "__main__":
    main()
