"""Quick script to investigate Yad2 pagination structure."""
import json
import pickle
import time
import random
from pathlib import Path

COOKIES_FILE = Path(__file__).parent / "cookies.pkl"

CHROME_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "DNT": "1",
}

base_url = "https://www.yad2.co.il/realestate/rent?topArea=2&area=1&city=5000&rooms=2.5-4&price=3000-7000"

from curl_cffi import requests

with requests.Session() as session:
    session.headers.update(CHROME_HEADERS)
    if COOKIES_FILE.exists():
        cookies = pickle.loads(COOKIES_FILE.read_bytes())
        session.cookies.update(cookies)

    # Warm up
    session.get("https://www.yad2.co.il/", impersonate="chrome", timeout=20)
    time.sleep(random.uniform(1.5, 3.0))

    for page in [1, 2]:
        url = f"{base_url}&page={page}"
        print(f"\n=== PAGE {page} ===")
        print(f"URL: {url}")

        resp = session.get(url, impersonate="chrome", timeout=30)
        html = resp.text

        marker = '<script id="__NEXT_DATA__" type="application/json">'
        start = html.find(marker)
        if start == -1:
            print("No __NEXT_DATA__ found!")
            continue
        start += len(marker)
        end = html.find("</script>", start)
        raw = html[start:end].strip()
        data = json.loads(raw)

        feed = data["props"]["pageProps"]["feed"]

        # Pagination info
        pagination = feed.get("pagination", {})
        print(f"Pagination: {json.dumps(pagination, indent=2)}")

        # Count items per category
        for cat in ["private", "agency", "platinum", "booster", "kingOfTheHar", "trio", "leadingBroker", "lookalike"]:
            items = feed.get(cat, [])
            if isinstance(items, list):
                print(f"  {cat}: {len(items)} items")

        # Show first 3 tokens from private to see ordering
        private = feed.get("private", [])
        print(f"\nFirst 3 private tokens: {[p.get('token') for p in private[:3]]}")
        print(f"First 3 private orderIds: {[p.get('orderId') for p in private[:3]]}")

        # Check search inputs
        inputs = data["props"]["pageProps"].get("initialSearchFormInputs", {})
        print(f"Search page input: {inputs.get('page')}")

        time.sleep(random.uniform(2, 4))
