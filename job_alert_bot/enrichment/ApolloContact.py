"""
HR/recruiter contact lookup via Apollo.io's People Search API
(https://api.apollo.io/v1/people/search), used as the SECOND provider
HrContact.py tries, after Hunter.io -- a separate free monthly credit
pool, so trying both roughly doubles how many new companies we can look
up for free each month.

Apollo is asked specifically for HR/recruiting/talent-acquisition job
titles at the given domain. On some plans Apollo returns a locked
placeholder (something like "email_not_unlocked@domain.com") instead of
a real address until it's explicitly "revealed" -- those are treated as
no result, never presented as a found contact.

NOTE: Apollo's API has changed shape across plan tiers before, so once
a real API key is in hand this should be tested against a live response
and adjusted if the field names below don't match what comes back --
the request/response handling here is deliberately isolated to this one
module so that's a small, contained fix if needed.

Returns {"email": str} (only when the email looks real and unlocked) or
None if no key is configured, nothing usable was found, or the request
failed.
"""
import requests

from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("enrichment.ApolloContact")

_PEOPLE_SEARCH_URL = "https://api.apollo.io/v1/people/search"
_HR_TITLES = ["Human Resources", "Recruiter", "Talent Acquisition", "HR Manager", "People Operations", "Hiring Manager"]
_LOCKED_EMAIL_MARKERS = ("not_unlocked", "email_not_unlocked", "locked")
_REQUEST_TIMEOUT_SECONDS = 10


def _looks_unlocked(email: str) -> bool:
    if not email or "@" not in email:
        return False
    lowered = email.lower()
    return not any(marker in lowered for marker in _LOCKED_EMAIL_MARKERS)


def find_contact(company_domain: str):
    if not Configuration.APOLLO_API_KEY:
        log.debug("Apollo.io lookup skipped for domain '%s' -- no API key configured.", company_domain)
        return None

    try:
        response = requests.post(
            _PEOPLE_SEARCH_URL,
            json={
                "api_key": Configuration.APOLLO_API_KEY,
                "q_organization_domains": company_domain,
                "person_titles": _HR_TITLES,
                "page": 1,
            },
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log.warning("Apollo.io request failed for domain '%s': %s", company_domain, exc)
        return None

    try:
        if response.status_code == 401:
            log.error("Apollo.io rejected the configured API key (401) -- check apollo_api_key in config.ini.")
            return None
        if response.status_code == 429:
            log.warning("Apollo.io rate-limited this lookup for domain '%s'.", company_domain)
            return None
        response.raise_for_status()

        payload = response.json()
        people = payload.get("people") or []

        for person in people:
            email = person.get("email")
            if _looks_unlocked(email):
                log.info("Apollo.io found a contact for domain '%s'.", company_domain)
                return {"email": email}

        log.info("Apollo.io had nothing usable (or only locked emails) for domain '%s'.", company_domain)
        return None

    except Exception as exc:
        log.error("Unexpected error parsing Apollo.io response for domain '%s': %s", company_domain, exc)
        return None
