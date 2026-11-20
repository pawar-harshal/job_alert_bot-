"""
Persists the most recent digest's numbered job entries so a later
Telegram /mail <number> command (see Commands.py) can map that number
back to the actual job data -- the digest text itself only shows a
number, title and summary, not the full row needed to draft an email.

Deliberately only the LATEST run's entries are usable by /mail at a
time, even though mail_command_history_runs exists in config.ini -- true
multi-run disambiguation would need run-ids in the /mail command syntax
itself (since display numbers restart at 1 each run), which isn't worth
the added complexity for a personal tool used by one person replying to
one digest at a time. Written fresh on every run that has new matches.
"""
import json
import os
from datetime import date, datetime

from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("telegram.MailMapping")


def _json_safe(value):
    """jobspy rows can contain pandas/datetime values that plain
    json.dump() can't serialize -- flatten anything non-primitive down
    to a string (or None for NaN) so the mapping always writes cleanly."""
    if isinstance(value, (datetime, date)):
        return str(value)
    if isinstance(value, float) and value != value:  # NaN != NaN
        return None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def save_run(numbered_jobs: dict):
    """numbered_jobs: {1: row_dict, 2: row_dict, ...} -- the same
    1-based numbering shown in that run's digest message."""
    try:
        safe_jobs = {
            str(number): {key: _json_safe(value) for key, value in row.items()}
            for number, row in numbered_jobs.items()
        }
        os.makedirs(os.path.dirname(Configuration.MAIL_MAPPING_PATH), exist_ok=True)
        with open(Configuration.MAIL_MAPPING_PATH, "w", encoding="utf-8") as f:
            json.dump({"jobs": safe_jobs}, f)
        log.debug("Saved mail mapping for %d job(s).", len(safe_jobs))
    except Exception as exc:
        # Not being able to persist the mapping just means /mail won't
        # work for this run's numbers -- not worth failing the whole
        # run over, so this is logged and swallowed.
        log.error("Failed to save mail mapping: %s", exc)


def get_job(number: int):
    try:
        if not os.path.exists(Configuration.MAIL_MAPPING_PATH):
            return None
        with open(Configuration.MAIL_MAPPING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("jobs", {}).get(str(number))
    except Exception as exc:
        log.warning("Failed to read mail mapping for job #%s: %s", number, exc)
        return None
