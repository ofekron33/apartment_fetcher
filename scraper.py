import json
import logging
import pickle
import re
import time
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

COOKIES_FILE = Path(__file__).parent / "cookies.pkl"

# Chrome-consistent headers — must match the TLS fingerprint identity
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


def _save_cookies(session) -> None:
    """Persist session cookies to disk."""
    try:
        cookies = dict(session.cookies)
        COOKIES_FILE.write_bytes(pickle.dumps(cookies))
        logger.debug("Saved %d cookies", len(cookies))
    except Exception as e:
        logger.warning("Failed to save cookies: %s", e)


def _load_cookies(session) -> bool:
    """Load cookies from disk into session. Returns True if loaded."""
    if not COOKIES_FILE.exists():
        return False
    try:
        cookies = pickle.loads(COOKIES_FILE.read_bytes())
        session.cookies.update(cookies)
        logger.debug("Loaded %d cookies", len(cookies))
        return True
    except Exception as e:
        logger.warning("Failed to load cookies: %s", e)
        return False


def _is_blocked(text: str) -> bool:
    """Check if the response is an anti-bot challenge page.

    Must be precise — "captcha" can appear in legit page JS bundles.
    A real block page is small (<20KB) and has ShieldSquare markers in the <title>.
    """
    # Real pages are large (100KB+), block pages are small
    if len(text) > 50000:
        return False
    # Check for specific block page markers
    markers = ["Are you for real", "<title>ShieldSquare Captcha</title>", "validate.perfdrive.com"]
    return any(m in text for m in markers)


def _extract_next_data(html: str) -> Optional[str]:
    """Extract __NEXT_DATA__ JSON string from HTML."""
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    start = html.find(marker)
    if start == -1:
        # Try alternate marker format
        marker = '<script id="__NEXT_DATA__"'
        start = html.find(marker)
        if start == -1:
            return None
        # Find the closing > of the script tag
        start = html.find(">", start) + 1
    else:
        start += len(marker)
    end = html.find("</script>", start)
    if end == -1:
        return None
    return html[start:end].strip()


def create_session():
    """Create a curl_cffi session with headers, cookies, and homepage warmup."""
    from curl_cffi import requests

    session = requests.Session()
    session.headers.update(CHROME_HEADERS)
    _load_cookies(session)

    # Warm up: visit homepage first to build cookie trust
    try:
        logger.debug("Warming up with homepage visit")
        session.get(
            "https://www.yad2.co.il/",
            impersonate="chrome",
            timeout=20,
        )
        time.sleep(random.uniform(1.5, 3.0))
    except Exception as e:
        logger.debug("Homepage warmup failed: %s", e)

    return session


def fetch_page(session, url: str) -> Optional[dict]:
    """Fetch a single page and extract __NEXT_DATA__. Returns parsed dict or None."""
    try:
        response = session.get(
            url,
            impersonate="chrome",
            timeout=30,
        )
    except Exception as e:
        logger.error("curl_cffi request failed: %s", e)
        return None

    html = response.text
    logger.debug("Response status: %d, length: %d", response.status_code, len(html))

    if _is_blocked(html):
        logger.warning("curl_cffi: blocked by anti-bot")
        return None

    _save_cookies(session)

    raw_json = _extract_next_data(html)
    if not raw_json:
        logger.warning("curl_cffi: __NEXT_DATA__ not found in response")
        _dump_debug(html, "debug_curl.html")
        return None

    try:
        data = json.loads(raw_json)
        logger.info("curl_cffi: extracted __NEXT_DATA__ (%d bytes)", len(raw_json))
        return data
    except json.JSONDecodeError as e:
        logger.error("curl_cffi: JSON parse error: %s", e)
        return None


def strip_page_param(url: str) -> str:
    """Remove any existing &page=N or ?page=N from the URL."""
    url = re.sub(r'[&?]page=\d+', '', url)
    # Clean up potential leftover ? at the end or ?& sequence
    url = url.replace('?&', '?')
    if url.endswith('?'):
        url = url[:-1]
    return url


def fetch_listing_details(session, tokens: list[str],
                          delay_range: tuple[float, float] = (1.0, 2.0)) -> dict[str, dict]:
    """Fetch detail pages for a list of listing tokens. Returns {token: detail_data}."""
    results = {}
    for i, token in enumerate(tokens):
        url = f"https://www.yad2.co.il/realestate/item/{token}"
        data = fetch_page(session, url)
        if data:
            # Extract the listing data from the detail page structure
            queries = (data.get("props", {}).get("pageProps", {})
                       .get("dehydratedState", {}).get("queries", []))
            for q in queries:
                item = q.get("state", {}).get("data")
                if isinstance(item, dict) and item.get("token") == token:
                    results[token] = item
                    break
        if i < len(tokens) - 1:
            time.sleep(random.uniform(*delay_range))
    logger.info("Fetched details for %d/%d listings", len(results), len(tokens))
    return results


def scrape_curl_cffi(url: str) -> Optional[dict]:
    """Primary method: curl_cffi with Chrome TLS impersonation."""
    logger.info("Trying curl_cffi with Chrome TLS impersonation...")
    session = create_session()
    try:
        return fetch_page(session, url)
    finally:
        session.close()


def scrape_uc(url: str) -> Optional[dict]:
    """Fallback method: undetected-chromedriver headless."""
    try:
        import undetected_chromedriver as uc
    except ImportError:
        logger.warning("undetected-chromedriver not installed, skipping fallback")
        return None

    logger.info("Trying undetected-chromedriver (headless)...")
    driver = None
    try:
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=he-IL")

        driver = uc.Chrome(options=options, version_main=148)

        # Warm up
        driver.get("https://www.yad2.co.il/")
        time.sleep(random.uniform(3, 5))

        driver.get(url)
        time.sleep(random.uniform(4, 6))

        page_source = driver.page_source or ""
        if _is_blocked(page_source):
            logger.warning("uc: blocked by anti-bot")
            return None

        raw_json = _extract_next_data(page_source)
        if not raw_json:
            logger.warning("uc: __NEXT_DATA__ not found")
            _dump_debug(page_source, "debug_uc.html")
            return None

        data = json.loads(raw_json)
        logger.info("uc: extracted __NEXT_DATA__ (%d bytes)", len(raw_json))
        return data

    except Exception as e:
        logger.error("uc: scrape failed: %s", e)
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def scrape(url: str) -> Optional[dict]:
    """Try scraping methods in order: curl_cffi first, then uc fallback."""
    # Method 1: curl_cffi (fast, lightweight)
    data = scrape_curl_cffi(url)
    if data:
        return data

    # Method 2: undetected-chromedriver (heavier, but passes more checks)
    data = scrape_uc(url)
    if data:
        return data

    logger.error("All scraping methods failed")
    return None


def _dump_debug(html: str, filename: str) -> None:
    """Dump response for debugging."""
    path = Path(filename)
    path.write_text(html[:50000], encoding="utf-8")
    logger.info("Dumped response to %s (%d chars)", path, len(html))
