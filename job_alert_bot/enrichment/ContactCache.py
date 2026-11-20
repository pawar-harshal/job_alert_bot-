"""
Persistent cache of HR/recruiter contacts already looked up, keyed by
company domain. Both Hunter.io and Apollo.io have tight free monthly
quotas (25 and a small monthly credit pool respectively) -- without this
cache, every new job at a company we've already looked up would burn
another credit for no reason. With it, each company is only ever looked
up once, however many times it shows up in future digests.

Same shape as dedupe/Store.py: a tiny SQLite-backed class, opened per
lookup (lookups are infrequent -- one per new company, not per job).
"""
import sqlite3
from typing import Optional

from job_alert_bot.utils.Logger import get_logger

log = get_logger("enrichment.ContactCache")


class ContactCache:
    def __init__(self, db_path):
        try:
            self._conn = sqlite3.connect(db_path)
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS hr_contacts (
                    domain TEXT PRIMARY KEY,
                    email TEXT,
                    verified INTEGER,
                    source TEXT,
                    profile_url TEXT,
                    looked_up_at TEXT DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            self._conn.commit()
        except Exception as exc:
            log.error("Failed to open/initialize contact cache database at '%s': %s", db_path, exc)
            raise

    def get(self, domain: str):
        try:
            cur = self._conn.execute(
                "SELECT email, verified, source, profile_url FROM hr_contacts WHERE domain = ?", (domain,)
            )
            row = cur.fetchone()
        except Exception as exc:
            # A cache-read failure shouldn't block a fresh lookup -- log
            # and let the caller fall through to the rest of the chain.
            log.warning("Contact cache read failed for domain '%s', will look up fresh: %s", domain, exc)
            return None

        if row is None:
            return None
        email, verified, source, profile_url = row
        return {"email": email, "verified": bool(verified), "source": source, "profile_url": profile_url}

    def set(self, domain: str, email: str, verified: bool, source: str, profile_url: Optional[str] = None):
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO hr_contacts (domain, email, verified, source, profile_url) VALUES (?, ?, ?, ?, ?)",
                (domain, email, int(verified), source, profile_url),
            )
            self._conn.commit()
        except Exception as exc:
            # Not being able to cache this result just means we might
            # look it up again next time -- not a reason to fail the
            # whole lookup, so this is logged and swallowed.
            log.warning("Failed to cache contact result for domain '%s': %s", domain, exc)

    def close(self):
        self._conn.close()
