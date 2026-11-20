"""
"X-ray search" for an HR/recruiter's public LinkedIn profile at a given
company, via Google's Custom Search JSON API
(https://developers.google.com/custom-search/v1/overview).

This NEVER talks to LinkedIn directly -- it only queries Google's own
search index for pages Google has already crawled from LinkedIn's
public profiles (a `site:linkedin.com/in ...` query), the same
technique recruiters use by hand. It does not log into LinkedIn, drive
a browser against it, or scrape it in any way, so there's no LinkedIn
ToS/detection risk here.

This is the PRIMARY HR-contact path (see HrContact.py) -- when it finds
a plausible person, HrContact.py hands their name + the company domain
to EmailGuesser, which asks Hunter.io's Email Finder to verify/produce
a real email address for that specific person. The Hunter.io domain
search and Apollo.io paths are the BACKUP, used only if this one (or
EmailGuesser) comes up empty.

Returns {"name": str, "title": str, "profile_url": str} for the
best-matching result, or None if no Google Search API key/engine ID is
configured, nothing relevant was found, or the request failed.
"""
from typing import Optional

import requests

from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("enrichment.LinkedInSearch")

_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
_HR_QUERY_TERMS = '("HR" OR "Human Resources" OR "Talent Acquisition" OR "Recruiter" OR "People Operations")'
_REQUEST_TIMEOUT_SECONDS = 10


def _parse_name_and_title(result_title: str):
    """
    Google's result titles for LinkedIn profiles are typically shaped
    like "John Doe - HR Manager - Acme Corp | LinkedIn" (the exact
    separators can vary). Best-effort split -- if this gets it wrong,
    the caller still has the profile_url as the reliable part.
    """
    cleaned = result_title.split("|")[0].strip()  # drop trailing "| LinkedIn"
    parts = [p.strip() for p in cleaned.split(" - ") if p.strip()]
    name = parts[0] if parts else cleaned
    title = parts[1] if len(parts) > 1 else ""
    return name, title


def find_hr_profile(company_name: str, company_domain: Optional[str] = None):
    if not Configuration.GOOGLE_SEARCH_API_KEY or not Configuration.GOOGLE_SEARCH_ENGINE_ID:
        log.debug("LinkedIn X-ray search skipped for '%s' -- Google search API not configured.", company_name)
        return None

    query = f'site:linkedin.com/in {_HR_QUERY_TERMS} "{company_name}"'
    try:
        response = requests.get(
            _SEARCH_URL,
            params={
                "key": Configuration.GOOGLE_SEARCH_API_KEY,
                "cx": Configuration.GOOGLE_SEARCH_ENGINE_ID,
                "q": query,
                "num": 5,
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log.warning("LinkedIn X-ray search request failed for '%s': %s", company_name, exc)
        return None

    try:
        if response.status_code == 403:
            log.error("Google Search API rejected the request (403) -- check google_search_api_key / quota.")
            return None
        if response.status_code == 429:
            log.warning("Google Search API rate-limited this lookup for '%s'.", company_name)
            return None
        response.raise_for_status()

        items = response.json().get("items") or []
        if not items:
            log.info("LinkedIn X-ray search found nothing for '%s'.", company_name)
            return None

        top = items[0]
        name, title = _parse_name_and_title(top.get("title", ""))
        profile_url = top.get("link", "")
        if not name or not profile_url:
            log.info("LinkedIn X-ray search result for '%s' didn't have a usable name/link.", company_name)
            return None

        log.info("LinkedIn X-ray search found a candidate HR contact for '%s': %s", company_name, name)
        return {"name": name, "title": title, "profile_url": profile_url}

    except Exception as exc:
        log.error("Unexpected error parsing Google Search API response for '%s': %s", company_name, exc)
        return None
