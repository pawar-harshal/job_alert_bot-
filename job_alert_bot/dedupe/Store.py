"""
SQLite-backed dedupe store.

Fixes a real bug found in an earlier version: that version only checked
"have we seen this job?" against the database, which is only written to
AFTER a whole run finishes. So if the SAME posting turned up under two
different search terms in one run (common -- e.g. a role matches both
"AI Engineer" and "GenAI Developer"), it got queued twice into that run's
digest. Store.is_new() here also checks an in-memory "seen this run" set,
so a job is only ever queued once per run, in addition to never repeating
across runs.
"""
import sqlite3

from job_alert_bot.utils.Logger import get_logger

log = get_logger("dedupe.Store")


def make_job_key(row: dict) -> str:
    """Stable dedupe key -- prefers the job's own URL; falls back to
    site+company+title so a dedupe check never crashes on a missing URL."""
    url = (row.get("job_url") or "").strip()
    if url:
        return url
    return f"{row.get('site','')}|{row.get('company','')}|{row.get('title','')}"


class Store:
    def __init__(self, db_path):
        try:
            self._conn = sqlite3.connect(db_path)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    job_key TEXT PRIMARY KEY,
                    title TEXT,
                    company TEXT,
                    site TEXT,
                    first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._conn.commit()
        except Exception as exc:
            log.error("Failed to open/initialize dedupe database at '%s': %s", db_path, exc)
            raise
        # In-run cache -- see module docstring for why this exists
        # alongside the persistent table.
        self._seen_this_run = set()

    def is_new(self, job_key: str) -> bool:
        if job_key in self._seen_this_run:
            return False
        cur = self._conn.execute("SELECT 1 FROM seen_jobs WHERE job_key = ?", (job_key,))
        return cur.fetchone() is None

    def mark_pending(self, job_key: str):
        """Call this as soon as a job is queued for alerting (before the
        alert actually sends), so later jobs in the SAME run that match
        the same job_key are recognised as duplicates immediately."""
        self._seen_this_run.add(job_key)

    def mark_seen(self, job_key: str, title: str, company: str, site: str):
        """Persist to the database -- call only once you know the job's
        alert (or filtered-out verdict) has been durably recorded."""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO seen_jobs (job_key, title, company, site) VALUES (?, ?, ?, ?)",
                (job_key, title, company, site),
            )
            self._conn.commit()
        except Exception as exc:
            log.error("Failed to persist seen-job record for '%s': %s", job_key, exc)
            raise
        self._seen_this_run.add(job_key)

    def close(self):
        self._conn.close()
