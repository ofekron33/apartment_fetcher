import logging
import sys
from collections import Counter
from datetime import datetime, timezone

import httpx

from models import ScoredListing

logger = logging.getLogger(__name__)


def _safe_print(text: str) -> None:
    """Print text handling Unicode on Windows consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        ))

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(message: str, bot_token: str, chat_id: str) -> bool:
    """Send a single message via Telegram Bot API. Returns True on success."""
    url = TELEGRAM_API.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                return True
            logger.error("Telegram API error %d: %s", resp.status_code, resp.text)
            return False
    except httpx.HTTPError as e:
        logger.error("Failed to send Telegram message: %s", e)
        return False


def _build_header(scored_listings: list[ScoredListing], use_emoji: bool) -> str:
    """Build a digest header message summarizing the batch."""
    total = len(scored_listings)
    source_counts = Counter(sl.listing.source for sl in scored_listings)
    scores = [sl.score for sl in scored_listings]
    min_score, max_score = min(scores), max(scores)

    icon = "\U0001f4e8" if use_emoji else "[DIGEST]"  # envelope emoji

    lines = [f"{icon} <b>{total} new listing{'s' if total != 1 else ''} found</b>"]

    source_parts = []
    for source in ["yad2", "4kirot"]:
        count = source_counts.get(source, 0)
        if count:
            source_parts.append(f"{source.capitalize()}: {count}")
    if source_parts:
        lines.append("Sources: " + ", ".join(source_parts))

    if min_score == max_score:
        lines.append(f"Score: {min_score}")
    else:
        lines.append(f"Score range: {min_score}\u2013{max_score}")

    return "\n".join(lines)


def send_digest(scored_listings: list[ScoredListing], bot_token: str, chat_id: str) -> int:
    """Send a header message followed by individual listing messages.

    Returns the number of listing messages successfully sent.
    """
    # Send header
    header = _build_header(scored_listings, use_emoji=True)
    if not send_telegram(header, bot_token, chat_id):
        logger.error("Failed to send digest header")

    # Send individual listings
    sent = 0
    for sl in scored_listings:
        message = sl.format_message(use_emoji=True)
        if send_telegram(message, bot_token, chat_id):
            sent += 1
            logger.info("Sent notification for listing %s", sl.listing.id)
        else:
            logger.error("Failed to notify for listing %s", sl.listing.id)
    return sent


def notify(scored_listings: list[ScoredListing], config: dict) -> int:
    """Send Telegram notifications: a digest header followed by each listing.

    Returns the number of listing messages successfully sent.
    """
    tg = config.get("telegram", {})
    bot_token = tg.get("bot_token", "")
    chat_id = tg.get("chat_id", "")

    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        logger.warning("Telegram bot token not configured, printing to console only")
        _safe_print(_build_header(scored_listings, use_emoji=False))
        _safe_print("=" * 40)
        for sl in scored_listings:
            _safe_print(sl.format_message(use_emoji=False))
            _safe_print("-" * 40)
        return 0

    if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
        logger.warning("Telegram chat_id not configured, printing to console only")
        _safe_print(_build_header(scored_listings, use_emoji=False))
        _safe_print("=" * 40)
        for sl in scored_listings:
            _safe_print(sl.format_message(use_emoji=False))
            _safe_print("-" * 40)
        return 0

    return send_digest(scored_listings, bot_token, chat_id)


def send_heartbeat(config: dict, yad2_count: int, kirot_count: int, notified: int) -> None:
    """Send a short status ping after every run so you know the bot is alive."""
    tg = config.get("telegram", {})
    bot_token = tg.get("bot_token", "")
    chat_id = tg.get("chat_id", "")

    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        return
    if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
        return

    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    total_new = yad2_count + kirot_count

    if notified > 0:
        # Already sent listing messages — no extra heartbeat needed
        return

    if total_new == 0:
        msg = f"\u2705 {now} — no new listings"
    else:
        msg = f"\u2705 {now} — {total_new} new (all filtered out)"

    send_telegram(msg, bot_token, chat_id)
