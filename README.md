# Apartment Alerts

Aggregates rental listings from multiple sources and sends Telegram notifications for new apartments that match your criteria. Runs every 10-15 minutes via scheduled task.

## Sources

### Yad2 (working)

1. **Scrape** (`scraper.py`) - Fetches the Yad2 search page using `curl_cffi` with Chrome TLS impersonation (falls back to `undetected-chromedriver`). Extracts the `__NEXT_DATA__` JSON from the page. Persists cookies between runs to avoid bot detection.
2. **Parse** (`parser.py`) - Extracts listing data (price, rooms, floor, elevator, parking, address, etc.) from Yad2's category-based feed structure.
3. **Deduplicate** (`state.py`) - Tracks seen listing IDs in `seen_listings.json` so you only get notified once per listing.
4. **Filter & Score** (`scorer.py`) - Hard filters remove bad matches (e.g. high floor without elevator). Soft scoring ranks the rest by parking, low floor, room count, and price.
5. **Notify** (`notifier.py`) - Sends each passing listing to Telegram via Bot API. Falls back to console output if Telegram isn't configured.

### 4kirot.com (in progress)

Fetches apartment listings from 4kirot.com, which aggregates posts from Facebook apartment groups in the Tel Aviv area. Listings include address, price, geocoded coordinates, realtor/private flag, and original Facebook post link.

- **`setup_token.py`** - One-time setup: opens a browser, user logs in with Gmail, extracts and saves a Firebase refresh token to `firebase_token.json`. Only needs to run once.
- **`fetch_apartments.py`** - Pure API fetch, no browser needed. Uses the saved refresh token to get a fresh Firebase ID token, calls the `fetchapartments` Cloud Function, deduplicates against `seen_4kirot.json`, and returns only new listings.

**Status:** API fetching and deduplication work. Still needed:
- Filtering and scoring to match Yad2 criteria
- Telegram notifications for new 4kirot listings
- Unified pipeline in `main.py` that runs both sources

## Files

| File | Purpose |
|---|---|
| `main.py` | Entry point - orchestrates the pipeline |
| `scraper.py` | Yad2 page fetching with anti-bot evasion |
| `parser.py` | Raw JSON to `Listing` objects |
| `models.py` | `Listing` and `ScoredListing` dataclasses |
| `state.py` | Seen-listing deduplication (JSON file) |
| `scorer.py` | Hard filters + soft scoring |
| `notifier.py` | Telegram Bot API notifications |
| `config.json` | All configuration (URL, filters, scoring, Telegram creds) |
| `run_crawler.bat` | Bat file for Windows Task Scheduler (run every 15 min) |
| `setup_token.py` | One-time Firebase token extraction for 4kirot.com |
| `fetch_apartments.py` | 4kirot.com API fetcher with deduplication (no browser) |
| `firebase_token.json` | Saved Firebase refresh token (do not commit) |
| `seen_4kirot.json` | Seen 4kirot listing IDs for deduplication |

## Setup

```
pip install -r requirements.txt
```

Edit `config.json` with your Yad2 search URL and Telegram bot credentials.

## Run

```
python main.py
```

Or schedule `run_crawler.bat` with Windows Task Scheduler to run every 15 minutes.

## Config

All in `config.json`:

- **yad2_url** - Yad2 search URL with your filters (area, rooms, price range)
- **telegram.bot_token** / **telegram.chat_id** - Telegram Bot API credentials
- **filters** - Hard filters (min rooms, max floor without elevator)
- **scoring** - Point values for parking, low floor, 3+ rooms, price range
- **debug** - Set `true` to dump raw feed data for troubleshooting
