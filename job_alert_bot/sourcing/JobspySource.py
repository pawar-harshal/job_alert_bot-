"""
Sourcing via python-jobspy -- LinkedIn, Indeed, and Naukri.

This is the "reactive" sourcing path (see design doc): one search per
configured term, each returning a pandas DataFrame of postings.

A single search-term failure (a rate limit, a timeout, a platform
hiccup) must never stop the other terms from running -- same "one bad
iteration shouldn't kill the rest" philosophy as TicketPilot's auto-reset
loop. A rate-limit-shaped failure is logged as a warning (expected,
recoverable by waiting) rather than an error (unexpected).
"""
import time

from jobspy import scrape_jobs

from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("sourcing.JobspySource")

_RATE_LIMIT_MARKERS = ("429", "rate limit", "too many requests", "blocked")


def _is_rate_limit_shaped(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def search_all_terms():
    """
    Runs scrape_jobs() once per configured search term, yielding each
    result row as a plain dict (so callers don't need to know about
    pandas). Paces itself between terms per Configuration.DELAY_BETWEEN_SEARCHES
    to reduce the chance of being rate-limited.
    """
    for term in Configuration.SEARCH_TERMS:
        log.info("Searching for: %s", term)
        try:
            jobs = scrape_jobs(
                site_name=Configuration.SITE_NAMES,
                search_term=term,
                location=Configuration.LOCATION,
                results_wanted=Configuration.RESULTS_WANTED,
                hours_old=Configuration.HOURS_OLD,
                country_indeed=Configuration.COUNTRY_INDEED,
                linkedin_fetch_description=Configuration.FETCH_FULL_DESCRIPTION,
                fetch_description=Configuration.FETCH_FULL_DESCRIPTION,
            )
        except Exception as exc:
            if _is_rate_limit_shaped(exc):
                log.warning("Rate-limited searching for '%s', skipping this term: %s", term, exc)
            else:
                log.error("scrape_jobs failed for term '%s': %s", term, exc)
            time.sleep(Configuration.DELAY_BETWEEN_SEARCHES)
            continue

        if jobs is None or jobs.empty:
            log.info("No results for '%s'.", term)
            time.sleep(Configuration.DELAY_BETWEEN_SEARCHES)
            continue

        for _, row in jobs.iterrows():
            yield row.to_dict()

        time.sleep(Configuration.DELAY_BETWEEN_SEARCHES)
