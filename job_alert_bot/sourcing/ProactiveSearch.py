"""
Broad web search for job postings that never show up on LinkedIn,
Indeed, or Naukri at all -- the part of the user's original manual
workflow (checking company sites and other boards directly) that
jobspy's structured scraping can't reach. Uses the same Google Custom
Search API as enrichment/LinkedInSearch.py and
enrichment/CareerPageFinder.py (GOOGLE_SEARCH_API_KEY /
GOOGLE_SEARCH_ENGINE_ID) -- no separate account needed.

QUOTA: Google's free tier is 100 queries/day, SHARED across all three
of those modules, not 100 each. One query per configured search term
here would burn most of a day's quota in a single run if JobAlertBot.py
fires every ~25 minutes via cron. So this self-throttles: it only
actually searches once per Configuration.PROACTIVE_SEARCH_INTERVAL_HOURS
(default 24h), persisting the last-run time to a small file, and yields
nothing (no error, just skips) on every call in between. Safe to leave
wired into JobAlertBot.py's regular run regardless of how often cron
fires it.

Results from a search snippet are lower-confidence than jobspy's
structured data -- there's no reliable company name in a plain search
result, so "company" is left blank here; downstream filtering/digest
code already handles a blank company gracefully.

Returns rows shaped the same as JobspySource's, so callers don't need
to know the difference.
"""
import os
import time

import requests

from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("sourcing.ProactiveSearch")

_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
_EXCLUDED_SITES = ("linkedin.com", "indeed.com", "naukri.com")
_REQUEST_TIMEOUT_SECONDS = 10
_DELAY_BETWEEN_QUERIES_SECONDS = 2
_LAST_RUN_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "proactive_search_last_run.txt"
)


def _hours_since_last_run() -> float:
    try:
        with open(_LAST_RUN_PATH, "r", encoding="utf-8") as f:
            last_run = float(f.read().strip())
        return (time.time() - last_run) / 3600
    except (FileNotFoundError, ValueError):
        return float("inf")  # never run before -- always due
    except Exception as exc:
        log.warning("Could not read proactive search throttle file, assuming it's due: %s", exc)
        return float("inf")


def _record_run_now():
    try:
        os.makedirs(os.path.dirname(_LAST_RUN_PATH), exist_ok=True)
        with open(_LAST_RUN_PATH, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception as exc:
        log.warning("Could not record proactive search run time (may re-run sooner than intended): %s", exc)


def _build_query(term: str) -> str:
    exclusions = " ".join(f"-site:{site}" for site in _EXCLUDED_SITES)
    # Location is a soft hint in the query text, not a hard filter --
    # this is a general web search, not jobspy's structured parameter.
    return f'"{term}" job opening {Configuration.LOCATION} {exclusions}'


def _row_from_search_result(item: dict) -> dict:
    return {
        "title": item.get("title", ""),
        "company": "",  # not reliably extractable from a search snippet
        "location": Configuration.LOCATION,
        "description": item.get("snippet", ""),
        "job_url": item.get("link", ""),
        "company_url": "",
        "site": "web_search",
        "date_posted": "",
    }


def search_all_terms():
    if not Configuration.GOOGLE_SEARCH_API_KEY or not Configuration.GOOGLE_SEARCH_ENGINE_ID:
        log.debug("Proactive web search skipped -- Google search API not configured.")
        return

    if _hours_since_last_run() < Configuration.PROACTIVE_SEARCH_INTERVAL_HOURS:
        log.debug("Proactive web search skipped -- ran within the last %d hour(s).", Configuration.PROACTIVE_SEARCH_INTERVAL_HOURS)
        return

    _record_run_now()  # mark now, so a crash mid-run still respects the throttle

    for term in Configuration.SEARCH_TERMS:
        log.info("Proactive web search for: %s", term)
        try:
            response = requests.get(
                _SEARCH_URL,
                params={
                    "key": Configuration.GOOGLE_SEARCH_API_KEY,
                    "cx": Configuration.GOOGLE_SEARCH_ENGINE_ID,
                    "q": _build_query(term),
                    "num": 10,
                },
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            log.warning("Proactive web search request failed for '%s': %s", term, exc)
            time.sleep(_DELAY_BETWEEN_QUERIES_SECONDS)
            continue

        try:
            if response.status_code == 429:
                log.warning("Google Search API quota exhausted -- stopping proactive search for this run.")
                return
            response.raise_for_status()
            items = response.json().get("items") or []
        except Exception as exc:
            log.error("Unexpected error parsing proactive search response for '%s': %s", term, exc)
            time.sleep(_DELAY_BETWEEN_QUERIES_SECONDS)
            continue

        for item in items:
            yield _row_from_search_result(item)

        time.sleep(_DELAY_BETWEEN_QUERIES_SECONDS)
