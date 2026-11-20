"""
job_alert_bot entrypoint -- runs one full sourcing + filtering + digest
cycle. Run on a schedule (cron) on the VM.

Run manually:
    python -m job_alert_bot.JobAlertBot

Run on a schedule (every 20-30 min) via cron:
    */25 * * * * /home/<user>/job_alert_bot/venv/bin/python -m job_alert_bot.JobAlertBot

Logging is file-only (see utils/Logger.py) -- nothing prints to the
terminal on a manual run. Check job_alert_bot/logs/job_alert_bot.log for
what happened during a run.

Reactive sourcing (LinkedIn + Indeed via jobspy) and proactive sourcing
(sourcing/ProactiveSearch.py, a broad web search catching postings that
never show up on LinkedIn/Indeed/Naukri at all) both feed the same
filter -> dedupe -> digest pipeline. For each newly matched job,
enrichment/CareerPageFinder.py tries to find its listing on the
company's own career page too. All three of ProactiveSearch,
CareerPageFinder, and enrichment/HrContact.py's primary (LinkedIn)
path share ONE Google Custom Search free quota (100 queries/day) --
ProactiveSearch self-throttles to once a day to protect that shared
pool; CareerPageFinder has no cache and is deliberately "best effort,
not every job" if the quota runs out mid-run. None of this needs a
Google key to be configured -- every one of these simply returns
nothing/None and is skipped cleanly if GOOGLE_SEARCH_API_KEY /
GOOGLE_SEARCH_ENGINE_ID are left blank in config.ini.

A single job failing to process (a malformed row, an unexpected field
type) must never crash the whole run -- it's logged and skipped, same
"one bad iteration shouldn't stop the rest" philosophy used throughout
TicketPilot (the auto-reset loop, the per-search-term handling in
JobspySource.py).
"""
from job_alert_bot.dedupe.Store import Store, make_job_key
from job_alert_bot.enrichment import CareerPageFinder, HrContact
from job_alert_bot.filtering import should_alert
from job_alert_bot.sourcing import JobspySource, ProactiveSearch
from job_alert_bot.telegram import Digest, MailMapping
from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("JobAlertBot")


def run_once():
    store = Store(Configuration.DEDUPE_DB_PATH)

    total_found = 0
    total_filtered_out = 0
    total_errors = 0
    pending_entries = []
    pending_job_keys = []  # kept in step with pending_entries
    pending_rows_by_number = {}  # 1-based digest number -> full row, for /mail

    def process(row: dict):
        nonlocal total_found, total_filtered_out, total_errors
        total_found += 1
        title = row.get("title")
        company = row.get("company")

        try:
            job_key = make_job_key(row)

            if not store.is_new(job_key):
                return

            passes, reason, exp_note = should_alert(row)
            if not passes:
                total_filtered_out += 1
                log.info("Filtered out: %s @ %s -- %s", title, company, reason)
                # Marked seen immediately -- no point re-evaluating a job
                # we've already judged, even though we didn't alert on it.
                store.mark_seen(job_key, row.get("title", ""), row.get("company", ""), row.get("site", ""))
                return

            # Mark pending RIGHT NOW (before the digest sends) so the same
            # job turning up again under a different search term later in
            # this same run is recognised as a duplicate immediately --
            # this is the fix for the in-run duplicate bug found during
            # testing.
            store.mark_pending(job_key)

            # Best-effort: try to find this job's listing on the
            # company's own career page too. Never required -- if the
            # search API isn't configured, or the quota's exhausted, or
            # nothing matches, the digest just shows the platform link
            # as before.
            try:
                domain = HrContact.domain_from_url(row.get("company_url"))
                career_page_url = CareerPageFinder.find_career_page_listing(company, title, domain)
                if career_page_url:
                    row["career_page_url"] = career_page_url
            except Exception as exc:
                log.warning("Career-page lookup failed for '%s' @ '%s', continuing without it: %s", title, company, exc)

            digest_number = len(pending_entries) + 1
            pending_entries.append(Digest.format_job_entry(digest_number, row, exp_note))
            pending_job_keys.append((job_key, row.get("title", ""), row.get("company", ""), row.get("site", "")))
            pending_rows_by_number[digest_number] = row
            log.info("Matched: %s @ %s", title, company)

        except Exception as exc:
            # A single malformed job must not take down the whole run --
            # log it with enough context to debug later, and move on.
            total_errors += 1
            log.error("Unexpected error processing job '%s' @ '%s': %s", title, company, exc)

    for row in JobspySource.search_all_terms():
        process(row)

    # Self-throttled internally (see ProactiveSearch.py) -- safe to call
    # every run regardless of cron frequency; it only actually searches
    # once per PROACTIVE_SEARCH_INTERVAL_HOURS and yields nothing
    # otherwise, including when no search API key is configured.
    for row in ProactiveSearch.search_all_terms():
        process(row)

    if pending_entries:
        # Saved before sending -- the digest numbers are already fixed
        # at this point, and /mail should work even if a later message
        # in a split digest fails to send.
        MailMapping.save_run(pending_rows_by_number)
        all_sent = Digest.send_digest(pending_entries)
        if all_sent:
            for job_key, title, company, site in pending_job_keys:
                store.mark_seen(job_key, title, company, site)
            log.info("Digest sent covering %d new job(s).", len(pending_entries))
        else:
            log.warning(
                "Digest send failed for at least one message -- jobs NOT marked as seen, "
                "they'll be retried next run."
            )
    else:
        log.info("No new matching jobs this run -- no digest sent.")

    store.close()
    log.info(
        "Run complete. Jobs scanned: %d, filtered out: %d, errors: %d, new matches: %d.",
        total_found, total_filtered_out, total_errors, len(pending_entries),
    )


if __name__ == "__main__":
    run_once()
