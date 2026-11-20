"""
Sourcing via python-jobspy -- LinkedIn, Indeed, and Naukri.

This is the "reactive" sourcing path (see design doc): one search per
configured term, each returning a pandas DataFrame of postings.

LinkedIn and the other configured sites are queried in SEPARATE
scrape_jobs() calls per term, deliberately. python-jobspy's
fetch_description flag is shared globally across every site in one
call -- its older linkedin_fetch_description flag is deprecated and can
only turn that shared flag ON, never off independently (see
jobspy/model.py's _merge_linkedin_fetch_description and
jobspy/linkedin/__init__.py's own check, which reads the shared flag
directly). So a single call with both LinkedIn and Indeed can't give
Indeed full descriptions while sparing LinkedIn the extra per-job
request that triggers LinkedIn's aggressive rate-limiting from a cloud
IP. Splitting into two calls is the only way to do that.

A single search-term (or single-site) failure (a rate limit, a timeout,
a platform hiccup) must never stop the rest from running -- same "one
bad iteration shouldn't kill the rest" philosophy as TicketPilot's
auto-reset loop. A rate-limit-shaped failure is logged as a warning
(expected, recoverable by waiting) rather than an error (unexpected).
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


def _run_search(term: str, site_names: list, fetch_description: bool):
    """Runs one scrape_jobs() call for a specific subset of sites, with
    its own fetch_description setting. Yields each result row as a
    plain dict. Never raises -- a failure here is logged and simply
    yields nothing for this (term, sites) combination."""
    if not site_names:
        return

    log.info("Searching %s for: %s", ",".join(site_names), term)
    try:
        jobs = scrape_jobs(
            site_name=site_names,
            search_term=term,
            location=Configuration.LOCATION,
            results_wanted=Configuration.RESULTS_WANTED,
            hours_old=Configuration.HOURS_OLD,
            country_indeed=Configuration.COUNTRY_INDEED,
            fetch_description=fetch_description,
        )
    except Exception as exc:
        if _is_rate_limit_shaped(exc):
            log.warning("Rate-limited searching %s for '%s', skipping: %s", site_names, term, exc)
        else:
            log.error("scrape_jobs failed for %s / '%s': %s", site_names, term, exc)
        return

    if jobs is None or jobs.empty:
        log.info("No results from %s for '%s'.", site_names, term)
        return

    for _, row in jobs.iterrows():
        yield row.to_dict()


def search_all_terms():
    """
    Runs scrape_jobs() for each configured search term, with LinkedIn
    split into its own call (see module docstring for why) so it can
    use a different, less request-heavy fetch_description setting than
    the rest of the configured sites. Paces itself between calls per
    Configuration.DELAY_BETWEEN_SEARCHES to reduce the chance of being
    rate-limited.
    """
    linkedin_sites = [s for s in Configuration.SITE_NAMES if s.strip().lower() == "linkedin"]
    other_sites = [s for s in Configuration.SITE_NAMES if s.strip().lower() != "linkedin"]

    for term in Configuration.SEARCH_TERMS:
        if linkedin_sites:
            yield from _run_search(term, linkedin_sites, Configuration.LINKEDIN_FETCH_FULL_DESCRIPTION)
            time.sleep(Configuration.DELAY_BETWEEN_SEARCHES)

        if other_sites:
            yield from _run_search(term, other_sites, Configuration.FETCH_FULL_DESCRIPTION)
            time.sleep(Configuration.DELAY_BETWEEN_SEARCHES)
