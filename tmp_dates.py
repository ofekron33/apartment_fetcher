"""Check for date fields and orderId ordering across pages."""
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

    session.get("https://www.yad2.co.il/", impersonate="chrome", timeout=20)
    time.sleep(random.uniform(1.5, 3.0))

    # Dump ALL fields of first item to find date fields
    resp = session.get(f"{base_url}&page=1", impersonate="chrome", timeout=30)
    html = resp.text
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    start = html.find(marker) + len(marker)
    end = html.find("</script>", start)
    data = json.loads(html[start:end].strip())

    feed = data["props"]["pageProps"]["feed"]
    private = feed.get("private", [])

    # Show ALL keys of first item
    print("=== ALL KEYS of first private listing ===")
    first = private[0]
    print(json.dumps(list(first.keys()), indent=2))

    # Look for any date-like fields
    print("\n=== First listing full dump (for date fields) ===")
    # Print only non-image fields to keep it readable
    clean = {k: v for k, v in first.items() if k != "metaData"}
    print(json.dumps(clean, ensure_ascii=True, indent=2))

    # Show orderId range across pages 1-3
    print("\n=== orderId ranges across pages ===")
    for page in [1, 2, 3]:
        url = f"{base_url}&page={page}"
        if page > 1:
            time.sleep(random.uniform(2, 3))
            resp = session.get(url, impersonate="chrome", timeout=30)
            html = resp.text
            start = html.find(marker) + len(marker)
            end = html.find("</script>", start)
            data = json.loads(html[start:end].strip())
            feed = data["props"]["pageProps"]["feed"]
            private = feed.get("private", [])

        ids = [p.get("orderId") for p in private]
        print(f"Page {page}: min={min(ids)}, max={max(ids)}, first 5={ids[:5]}, last 5={ids[-5:]}")
