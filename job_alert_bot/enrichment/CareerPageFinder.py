"""
Finds a matched job's real listing on the company's OWN career page --
not just the LinkedIn/Indeed/Naukri posting -- so the digest can link
straight to where the user actually wants to apply (this is the "check
the company's own career page for the same listing" half of the user's
original manual workflow). Uses the same Google Custom Search API as
sourcing/ProactiveSearch.py and enrichment/LinkedInSearch.py
(GOOGLE_SEARCH_API_KEY / GOOGLE_SEARCH_ENGINE_ID) -- no separate
account needed.

QUOTA: shares the same 100-queries/day free pool as those two modules.
Unlike enrichment/HrContact.py's per-domain cache, there's no caching
here -- every job posting is different, so this is the path most likely
to run the quota out first if a run has many new matches. This is
intentionally "best effort, not every job" rather than guaranteed --
when the quota's exhausted (or no key is configured), this just returns
None and the digest shows the original platform link only, same as
today.

Never guesses a URL -- only returns what an actual search result found.
"""
from typing import Optional

import requests

from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("enrichment.CareerPageFinder")

_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
_REQUEST_TIMEOUT_SECONDS = 10


def find_career_page_listing(company: str, job_title: str, company_domain: Optional[str] = None):
    if not Configuration.GOOGLE_SEARCH_API_KEY or not Configuration.GOOGLE_SEARCH_ENGINE_ID:
        log.debug("Career-page lookup skipped for '%s' / '%s' -- Google search API not configured.", company, job_title)
        return None

    if not company and not job_title:
        return None

    # Restricting to the company's own domain when known gives a much
    # more targeted result than a plain web-wide search.
    query = f'site:{company_domain} "{job_title}"' if company_domain else f'"{company}" careers "{job_title}"'

    try:
        response = requests.get(
            _SEARCH_URL,
            params={
                "key": Configuration.GOOGLE_SEARCH_API_KEY,
                "cx": Configuration.GOOGLE_SEARCH_ENGINE_ID,
                "q": query,
                "num": 3,
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log.warning("Career-page search request failed for '%s' / '%s': %s", company, job_title, exc)
        return None

    try:
        if response.status_code == 429:
            log.warning("Google Search API quota exhausted -- skipping career-page lookup for '%s'.", company)
            return None
        response.raise_for_status()

        items = response.json().get("items") or []
        if not items:
            log.info("No career-page match found for '%s' / '%s'.", company, job_title)
            return None

        url = items[0].get("link")
        log.info("Found a likely career-page listing for '%s' / '%s'.", company, job_title)
        return url

    except Exception as exc:
        log.error("Unexpected error parsing career-page search response for '%s' / '%s': %s", company, job_title, exc)
        return None
