# Apartment Alerts

Aggregates rental listings from multiple sources and sends Telegram notifications for new apartments that match your criteria. Runs every 15 minutes via GitHub Actions.

## Sources

### Yad2

Scrapes Yad2 search results using `curl_cffi` with Chrome TLS impersonation (falls back to `undetected-chromedriver`). Supports multi-page pagination with resume state.

### 4kirot.com

Fetches apartment listings from 4kirot.com, which aggregates posts from Facebook apartment groups in the Tel Aviv area. Uses Firebase auth (refresh token) to call their API directly — no browser needed.

## Pipeline

1. **Scrape/Fetch** (`scraper.py`, `fetch_apartments.py`) — Collect listings from all sources
2. **Parse** (`parser.py`) — Extract structured data (price, rooms, floor, elevator, parking, address, etc.)
3. **Deduplicate** (`state.py`, `fetch_apartments.py`) — Track seen listing IDs so you only get notified once
4. **Filter & Score** (`scorer.py`) — Hard filters remove bad matches, soft scoring ranks the rest
5. **Enrich** — Fetch Yad2 detail pages for description, dates, expiry detection
6. **Notify** (`notifier.py`) — Send each passing listing to Telegram via Bot API

## Files

| File | Purpose |
|---|---|
| `main.py` | Entry point — orchestrates the full pipeline |
| `scraper.py` | Yad2 page fetching with anti-bot evasion |
| `parser.py` | Raw JSON to `Listing` objects |
| `models.py` | `Listing` and `ScoredListing` dataclasses |
| `state.py` | Seen-listing deduplication (JSON file) |
| `scorer.py` | Hard filters + soft scoring |
| `notifier.py` | Telegram Bot API notifications |
| `fetch_apartments.py` | 4kirot.com API fetcher with deduplication |
| `setup_token.py` | One-time Firebase token extraction for 4kirot.com |
| `config.json` | All configuration (URL, filters, scoring, Telegram creds) — not committed |

## Setup

### GitHub Actions (recommended)

The scraper runs automatically every 15 minutes via GitHub Actions.

1. Fork or clone this repo
2. Run `setup_token.py` once locally to log in and generate `firebase_token.json`
3. Add two repository secrets in **Settings > Secrets and variables > Actions**:
   - `CONFIG_JSON` — contents of your `config.json`
   - `FIREBASE_TOKEN_JSON` — contents of your `firebase_token.json`
4. Push to GitHub — the workflow runs automatically on schedule

State files (`seen_listings.json`, `seen_4kirot.json`, `pagination_state.json`, `firebase_token.json`) are persisted in a separate `state` git branch between runs.

### Local

```
pip install -r requirements.txt
python main.py
```

Or schedule `run_crawler.bat` with Windows Task Scheduler.

## Config

All in `config.json`:

- **yad2_url** — Yad2 search URL with your filters (area, rooms, price range)
- **pagination.max_pages** — How many pages to scrape per run
- **telegram.bot_token** / **telegram.chat_id** — Telegram Bot API credentials
- **filters** — Hard filters (min rooms, max floor without elevator)
- **scoring** — Point values for parking, low floor, 3+ rooms, price range
- **debug** — Set `true` to dump raw feed data for troubleshooting
