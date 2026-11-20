"""
Interactive Telegram command: replying "/mail <number>" against a
digest asks the bot to look up that numbered job, find (or guess) its
HR contact via enrichment/HrContact.py, draft an outreach email via
email_drafting/Draft.py, and send the result back as a Telegram message
-- for the user to review, edit, and send themselves via Gmail with
their resume attached. This never sends anything on the user's behalf.

Unlike JobAlertBot.py (a one-shot cron job), this needs to keep running
and listening for incoming messages -- run it as its OWN long-lived
process, separately from the cron schedule:

    python -m job_alert_bot.telegram.Commands

(under systemd, screen, or tmux on the VM -- see README.)

Uses Telegram's getUpdates long-polling endpoint. A single bad/malformed
incoming update, or a failure handling one /mail command, must never
kill the whole listener -- same "one bad item never stops the rest"
philosophy as the rest of the codebase.
"""
import time

import requests

from job_alert_bot.email_drafting import Draft
from job_alert_bot.enrichment import HrContact
from job_alert_bot.telegram import MailMapping
from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("telegram.Commands")

_GET_UPDATES_URL_TEMPLATE = "https://api.telegram.org/bot{token}/getUpdates"
_SEND_MESSAGE_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
_POLL_TIMEOUT_SECONDS = 30  # how long Telegram holds the long-poll connection open
_POLL_ERROR_BACKOFF_SECONDS = 10


def _send_reply(text: str):
    try:
        resp = requests.post(
            _SEND_MESSAGE_URL_TEMPLATE.format(token=Configuration.TELEGRAM_BOT_TOKEN),
            data={"chat_id": Configuration.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.error("Failed to send Telegram reply: %s", exc)


def _parse_mail_command(text: str):
    """Returns the job number if text is a "/mail <number>" command
    (tolerating a bot-username suffix like "/mail@MyBot 3"), else
    None -- None means "not a /mail command", not an error."""
    if not text:
        return None
    parts = text.strip().split()
    if len(parts) != 2 or not parts[0].lower().startswith("/mail"):
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def handle_mail_command(job_number: int):
    job = MailMapping.get_job(job_number)
    if job is None:
        _send_reply(f"Couldn't find job #{job_number} from the most recent digest -- it may be from an older run.")
        return

    title = job.get("title") or "the role"
    company = job.get("company") or "the company"

    domain = HrContact.domain_from_url(job.get("company_url"))
    contact = HrContact.find_hr_contact(company, domain) if domain else None
    contact_email = contact["email"] if contact else None

    drafted = Draft.draft_email(job, contact_email or "")
    if drafted is None:
        _send_reply(f"Couldn't draft an email for #{job_number} ({title} @ {company}) right now -- try again shortly.")
        return

    if contact_email:
        confidence = "verified" if contact.get("verified") else "unverified guess"
        contact_line = f"Contact: {contact_email} ({confidence})"
    else:
        contact_line = "Contact: not found -- you'll need to find one yourself."
    profile_line = f"\nLinkedIn: {contact['profile_url']}" if contact and contact.get("profile_url") else ""

    reply = (
        f"✉️ Drafted email for #{job_number} -- {title} @ {company}\n"
        f"{contact_line}{profile_line}\n\n"
        f"Subject: {drafted['subject']}\n\n"
        f"{drafted['body']}"
    )
    _send_reply(reply)
    log.info("Replied with a drafted email for job #%d (%s @ %s).", job_number, title, company)


def _process_update(update: dict):
    message = update.get("message") or {}
    text = message.get("text", "")

    job_number = _parse_mail_command(text)
    if job_number is None:
        return  # Not a /mail command -- not an error, just ignore it.

    log.info("Received /mail command for job #%d.", job_number)
    try:
        handle_mail_command(job_number)
    except Exception as exc:
        # A single bad command must never kill the listener.
        log.error("Unexpected error handling /mail %d: %s", job_number, exc)
        _send_reply(f"Something went wrong drafting job #{job_number} -- check the logs.")


def run_polling_loop():
    log.info("Starting Telegram command listener (long-polling)...")
    offset = None

    while True:
        try:
            params = {"timeout": _POLL_TIMEOUT_SECONDS}
            if offset is not None:
                params["offset"] = offset

            resp = requests.get(
                _GET_UPDATES_URL_TEMPLATE.format(token=Configuration.TELEGRAM_BOT_TOKEN),
                params=params,
                timeout=_POLL_TIMEOUT_SECONDS + 10,
            )
            resp.raise_for_status()
            payload = resp.json()

            if not payload.get("ok"):
                log.warning("Telegram getUpdates returned ok=false: %s", payload)
                time.sleep(_POLL_ERROR_BACKOFF_SECONDS)
                continue

            for update in payload.get("result", []):
                offset = update["update_id"] + 1
                try:
                    _process_update(update)
                except Exception as exc:
                    # One malformed update must never stop the listener
                    # from processing the rest, or future ones.
                    log.error("Unexpected error processing update %s: %s", update.get("update_id"), exc)

        except requests.RequestException as exc:
            log.warning("Telegram getUpdates request failed, retrying: %s", exc)
            time.sleep(_POLL_ERROR_BACKOFF_SECONDS)
        except Exception as exc:
            log.error("Unexpected error in polling loop: %s", exc)
            time.sleep(_POLL_ERROR_BACKOFF_SECONDS)


if __name__ == "__main__":
    run_polling_loop()
