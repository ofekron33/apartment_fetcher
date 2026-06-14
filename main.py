import json
import logging
import sys
from pathlib import Path

import random
import time

from datetime import date

from scraper import scrape, create_session, fetch_page, fetch_listing_details, strip_page_param
from parser import parse_listings, extract_pagination_info
from state import load_seen_ids, save_seen_ids, load_resume_page, save_resume_page, filter_new
from scorer import filter_and_score
from notifier import notify, send_heartbeat
from fetch_apartments import (
    get_id_token,
    fetch_apartments as fetch_4kirot,
    filter_new as filter_new_4kirot,
    apartments_to_listings,
)

CONFIG_FILE = Path(__file__).parent / "config.json"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"Config file not found: {CONFIG_FILE}")
        sys.exit(1)
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_yad2(config: dict, debug: bool, logger) -> list:
    """Scrape Yad2 and return new (unseen) Listing objects."""
    url = config.get("yad2_url", "")
    if not url:
        logger.info("No yad2_url configured, skipping Yad2")
        return []

    pagination = config.get("pagination", {})
    max_pages = pagination.get("max_pages", 1)
    delay_min = pagination.get("delay_min", 2.0)
    delay_max = pagination.get("delay_max", 5.0)

    if max_pages > 1:
        previously_seen = load_seen_ids()
        resume_page = load_resume_page()
        base_url = strip_page_param(url)
        separator = "&" if "?" in base_url else "?"

        listings = []
        dedup_ids = set()
        pages_scraped = 0
        pages_with_new = 0
        pag_info = None
        deepest_page = resume_page

        def _scrape_page(session, page_num):
            nonlocal pag_info, pages_scraped, pages_with_new, deepest_page
            page_url = f"{base_url}{separator}page={page_num}" if page_num > 1 else base_url

            page_data = fetch_page(session, page_url)
            if page_data is None:
                return None

            pages_scraped += 1
            if pag_info is None:
                pag_info = extract_pagination_info(page_data)

            page_listings = parse_listings(page_data, debug=(debug and page_num == 1))
            unseen_on_page = 0
            for listing in page_listings:
                if listing.id not in dedup_ids:
                    dedup_ids.add(listing.id)
                    if listing.id not in previously_seen:
                        listings.append(listing)
                        unseen_on_page += 1

            logger.info("Page %d: %d parsed, %d new",
                        page_num, len(page_listings), unseen_on_page)
            if unseen_on_page > 0:
                pages_with_new += 1
            if page_num > deepest_page:
                deepest_page = page_num
            return unseen_on_page

        session = create_session()
        try:
            logger.info("Phase 1: checking for new listings (starting from page 1)...")
            for page_num in range(1, (resume_page or max_pages) + 1):
                if pag_info and pag_info.get("total_pages") and page_num > pag_info["total_pages"]:
                    break
                logger.info("Fetching page %d", page_num)
                unseen = _scrape_page(session, page_num)
                if unseen is None:
                    break
                if unseen == 0 and page_num > 1:
                    logger.info("Page %d had 0 new listings — caught up with new listings", page_num)
                    break
                time.sleep(random.uniform(delay_min, delay_max))

            if pages_with_new < max_pages:
                total_pages = pag_info.get("total_pages") if pag_info else None
                start_from = deepest_page + 1
                if total_pages and start_from <= total_pages:
                    logger.info("Phase 2: expanding coverage (resuming from page %d)...", start_from)
                    for page_num in range(start_from, (total_pages or start_from + max_pages) + 1):
                        if pages_with_new >= max_pages:
                            break
                        if total_pages and page_num > total_pages:
                            break
                        logger.info("Fetching page %d (found new on %d/%d so far)",
                                    page_num, pages_with_new, max_pages)
                        unseen = _scrape_page(session, page_num)
                        if unseen is None:
                            break
                        time.sleep(random.uniform(delay_min, delay_max))
                else:
                    logger.info("Phase 2: all %s pages already covered", total_pages)
        finally:
            session.close()

        save_resume_page(deepest_page)
        listings.sort(key=lambda l: l.order_id or 0, reverse=True)

        if pag_info:
            total_on_yad2 = pag_info["total"]
            total_pages = pag_info.get("total_pages", "?")
            logger.info("Yad2 has %d total listings across %s pages — scraped %d pages "
                        "(%d had new), got %d new listings, covered up to page %d",
                        total_on_yad2, total_pages, pages_scraped, pages_with_new,
                        len(listings), deepest_page)
    else:
        logger.info("Fetching listings from yad2...")
        data = scrape(url)
        if data is None:
            logger.warning("Yad2: failed to fetch data, will retry next cycle")
            return []
        listings = parse_listings(data, debug=debug)

        pag_info = extract_pagination_info(data)
        if pag_info:
            total_on_yad2 = pag_info["total"]
            total_pages = pag_info.get("total_pages", "?")
            remaining = total_on_yad2 - len(listings)
            logger.info("Yad2 has %d total listings across %s pages — scraped 1 page, "
                        "got %d listings, ~%d remaining",
                        total_on_yad2, total_pages, len(listings), max(remaining, 0))

    if not listings:
        logger.info("Yad2: no listings parsed")
        return []

    logger.info("Yad2: parsed %d total listings", len(listings))

    new_listings = filter_new(listings)
    logger.info("Yad2: %d new listings", len(new_listings))
    return new_listings


def run_4kirot(config: dict, logger) -> list:
    """Fetch 4kirot listings and return new (unseen) Listing objects."""
    logger.info("Fetching listings from 4kirot...")
    try:
        id_token = get_id_token()
    except FileNotFoundError:
        logger.info("4kirot: no firebase_token.json found, skipping (run setup_token.py to set up)")
        return []

    if not id_token:
        logger.warning("4kirot: token refresh failed, skipping")
        return []

    apartments = fetch_4kirot(id_token)
    if apartments is None:
        logger.warning("4kirot: API fetch failed, skipping")
        return []

    logger.info("4kirot: got %d apartments from API", len(apartments))

    new_apartments = filter_new_4kirot(apartments)
    if not new_apartments:
        logger.info("4kirot: no new listings")
        return []

    listings = apartments_to_listings(new_apartments)
    logger.info("4kirot: %d new listings", len(listings))
    return listings


def run() -> None:
    config = load_config()
    debug = config.get("debug", False)
    setup_logging(debug)
    logger = logging.getLogger(__name__)

    # Collect new listings from all sources
    all_new = []

    # Source 1: Yad2
    yad2_new = run_yad2(config, debug, logger)
    all_new.extend(yad2_new)

    # Source 2: 4kirot
    kirot_new = run_4kirot(config, logger)
    all_new.extend(kirot_new)

    if not all_new:
        logger.info("No new listings from any source")
        send_heartbeat(config, len(yad2_new), len(kirot_new), notified=0)
        return
    logger.info("Total new listings across all sources: %d (Yad2: %d, 4kirot: %d)",
                len(all_new), len(yad2_new), len(kirot_new))

    # Filter & Score
    scored = filter_and_score(all_new, config)
    if not scored:
        logger.info("All new listings filtered out by hard filters")
        send_heartbeat(config, len(yad2_new), len(kirot_new), notified=0)
        return
    logger.info("%d listings passed filters, top score: %d", len(scored), scored[0].score)

    # Enrich Yad2 listings with detail pages (4kirot doesn't have detail pages)
    yad2_scored = [sl for sl in scored if sl.listing.source == "yad2"]
    if yad2_scored:
        logger.info("Fetching detail pages for %d Yad2 listings...", len(yad2_scored))
        detail_session = create_session()
        try:
            tokens = [sl.listing.id for sl in yad2_scored]
            details = fetch_listing_details(detail_session, tokens)
        finally:
            detail_session.close()

        today = date.today().isoformat()
        expired_ids = []
        for sl in yad2_scored:
            detail = details.get(sl.listing.id)
            if detail:
                desc = (detail.get("metaData", {}).get("description")
                        or detail.get("furnitureInfo") or "")
                sl.listing.description = desc
                entrance = detail.get("additionalDetails", {}).get("entranceDate")
                if entrance:
                    sl.listing.entrance_date = entrance
                dates = detail.get("dates", {})
                sl.listing.created_at = dates.get("createdAt")
                sl.listing.updated_at = dates.get("updatedAt")
                sl.listing.rebounced_at = dates.get("rebouncedAt")
                ends_at = dates.get("endsAt")
                if ends_at:
                    sl.listing.ends_at = ends_at
                    if ends_at[:10] < today:
                        logger.info("Skipping expired listing %s (ended %s)", sl.listing.id, ends_at[:10])
                        expired_ids.append(sl.listing.id)

        if expired_ids:
            seen = load_seen_ids()
            for eid in expired_ids:
                seen.pop(eid, None)
            save_seen_ids(seen)
            logger.info("Unmarked %d expired listings from seen state", len(expired_ids))

        expired_set = set(expired_ids)
        scored = [sl for sl in scored if sl.listing.id not in expired_set]

    if not scored:
        logger.info("All scored listings were expired")
        send_heartbeat(config, len(yad2_new), len(kirot_new), notified=0)
        return

    # Notify
    sent = notify(scored, config)
    if sent:
        logger.info("Sent %d Telegram notifications", sent)
    else:
        logger.info("Notifications printed to console (Telegram not configured or send failed)")

    send_heartbeat(config, len(yad2_new), len(kirot_new), notified=sent)


if __name__ == "__main__":
    run()
