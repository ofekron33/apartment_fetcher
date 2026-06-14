import logging
import sys

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


def notify(scored_listings: list[ScoredListing], config: dict) -> int:
    """Send Telegram notifications for each scored listing.

    Returns the number of messages successfully sent.
    """
    tg = config.get("telegram", {})
    bot_token = tg.get("bot_token", "")
    chat_id = tg.get("chat_id", "")

    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        logger.warning("Telegram bot token not configured, printing to console only")
        for sl in scored_listings:
            _safe_print(sl.format_message(use_emoji=False))
            _safe_print("-" * 40)
        return 0

    if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
        logger.warning("Telegram chat_id not configured, printing to console only")
        for sl in scored_listings:
            _safe_print(sl.format_message(use_emoji=False))
            _safe_print("-" * 40)
        return 0

    sent = 0
    for sl in scored_listings:
        message = sl.format_message(use_emoji=True)
        if send_telegram(message, bot_token, chat_id):
            sent += 1
            logger.info("Sent notification for listing %s", sl.listing.id)
        else:
            logger.error("Failed to notify for listing %s", sl.listing.id)
    return sent
