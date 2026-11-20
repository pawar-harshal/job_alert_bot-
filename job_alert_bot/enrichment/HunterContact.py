"""
HR/recruiter contact lookup via Hunter.io's Domain Search API
(https://api.hunter.io/v2/domain-search).

Given a company domain, asks Hunter.io for every email address it has on
file for that domain, then prefers one that actually looks HR/recruiting
related (department/position mentioning hr/recruiter/talent/people) over
just picking the first result, falling back to a "generic" (info@/hr@
style) address if nothing more specific is found.

This is ONE of the providers HrContact.py tries, in order -- this module
knows nothing about Apollo.io, caching, or the careers@ guess fallback;
that orchestration lives in HrContact.py. Returns {"email": str} (always
verified, since every match here is a real contact Hunter.io has on
file) or None if no key is configured, nothing was found, or the request
failed.
"""
from typing import Optional

import requests

from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("enrichment.HunterContact")

_DOMAIN_SEARCH_URL = "https://api.hunter.io/v2/domain-search"
_HR_RELEVANT_MARKERS = ("hr", "recruit", "talent", "people", "hiring")
_REQUEST_TIMEOUT_SECONDS = 10


def _pick_best_email(emails: list) -> Optional[dict]:
    generic_fallback = None
    for entry in emails:
        value = entry.get("value")
        if not value:
            continue

        department = (entry.get("department") or "").lower()
        position = (entry.get("position") or "").lower()
        if any(marker in department or marker in position for marker in _HR_RELEVANT_MARKERS):
            return entry

        if entry.get("type") == "generic" and generic_fallback is None:
            generic_fallback = entry

    return generic_fallback


def find_contact(company_domain: str):
    if not Configuration.HUNTER_API_KEY:
        log.debug("Hunter.io lookup skipped for domain '%s' -- no API key configured.", company_domain)
        return None

    try:
        response = requests.get(
            _DOMAIN_SEARCH_URL,
            params={"domain": company_domain, "api_key": Configuration.HUNTER_API_KEY},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        # Network-level failure -- expected to happen occasionally,
        # recoverable by just trying Apollo next or again later.
        log.warning("Hunter.io request failed for domain '%s': %s", company_domain, exc)
        return None

    try:
        if response.status_code == 401:
            log.error("Hunter.io rejected the configured API key (401) -- check hunter_api_key in config.ini.")
            return None
        if response.status_code == 429:
            log.warning("Hunter.io rate-limited this lookup for domain '%s'.", company_domain)
            return None
        response.raise_for_status()

        payload = response.json()
        emails = (payload.get("data") or {}).get("emails") or []

        best = _pick_best_email(emails)
        if best is not None:
            log.info("Hunter.io found a contact for domain '%s'.", company_domain)
            return {"email": best["value"]}

        log.info("Hunter.io had nothing usable for domain '%s'.", company_domain)
        return None

    except Exception as exc:
        # Unexpected response shape/bad JSON -- fail safe, don't crash.
        log.error("Unexpected error parsing Hunter.io response for domain '%s': %s", company_domain, exc)
        return None
