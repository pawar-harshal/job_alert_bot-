"""
Formats a run's matching jobs into as few Telegram messages as possible
(ideally one) and sends them.
"""
import time

import requests

from job_alert_bot.filtering import Location
from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("telegram.Digest")

# Telegram's hard limit on a single message's text.
TELEGRAM_MAX_MESSAGE_LEN = 4096


def send_message(text: str) -> bool:
    url = f"https://api.telegram.org/bot{Configuration.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={
                "chat_id": Configuration.TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("ok"):
            log.error("Telegram API returned ok=false: %s", payload)
            return False
        return True
    except Exception as exc:
        log.error("Failed to send Telegram message: %s", exc)
        return False


def format_job_entry(index: int, row: dict, experience_note: str) -> str:
    """
    Deliberately minimal: title, company, location, source, and the
    platform link only. No description snippet, experience note,
    career-page line, or HR-contact line -- kept out of the alert text
    on purpose (short, scannable message), even though all of that is
    still computed elsewhere (career_page_url, hr_contact) for /mail
    and logging to use.
    """
    title = row.get("title") or "Untitled role"
    company = row.get("company") or "Unknown company"
    loc = row.get("location") or "Location not listed"
    site = (row.get("site") or "").upper()
    url = row.get("job_url") or ""
    date_posted = row.get("date_posted") or "unknown date"
    remote_tag = " · Remote" if Location.is_remote(row) else ""

    lines = [
        f"{index}. <b>{title}</b>",
        f"🏢 {company}",
        f"📍 {loc}{remote_tag}",
        f"🌐 Source: {site}  ·  Posted: {date_posted}",
    ]
    if url:
        lines.append(f"🔗 Platform: {url}")

    return "\n".join(lines)


def build_digest_messages(entries: list) -> list:
    """
    Combines every job entry into as few messages as possible -- splits
    only if the combined text would exceed Telegram's per-message length
    limit; a job entry is never cut mid-way.
    """
    if not entries:
        return []

    header = f"📋 <b>Job Alert Digest — {len(entries)} new match(es)</b>\n"
    separator = "\n\n" + ("—" * 20) + "\n\n"

    messages = []
    current = header
    current_has_entries = False

    for entry in entries:
        piece = entry if not current_has_entries else (separator + entry)
        if current_has_entries and (len(current) + len(piece) > TELEGRAM_MAX_MESSAGE_LEN):
            messages.append(current)
            current = entry
            current_has_entries = True
            continue
        current += piece
        current_has_entries = True

    if current_has_entries:
        messages.append(current)

    return messages


def send_digest(entries: list) -> bool:
    """Sends every message in the digest. Returns True only if ALL of
    them sent successfully -- callers should not mark jobs as seen on a
    partial failure, so nothing is silently lost."""
    messages = build_digest_messages(entries)
    all_sent = True
    for i, msg in enumerate(messages, start=1):
        if not send_message(msg):
            all_sent = False
            log.warning("Failed to send digest message %d/%d.", i, len(messages))
        time.sleep(1)
    return all_sent
