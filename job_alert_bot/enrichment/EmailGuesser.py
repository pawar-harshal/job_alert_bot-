"""
Turns a person's name + company domain into a verified email address,
via Hunter.io's Email Finder endpoint
(https://api.hunter.io/v2/email-finder).

This is deliberately NOT a hand-rolled pattern guesser (first.last@,
flast@, etc. tried one by one) -- Hunter's Email Finder already does
that internally against real patterns it has seen for the domain, and
returns a confidence score plus (when possible) a deliverability
verification, in a single call. Reusing their algorithm is both more
accurate and cheaper on quota than reimplementing it ourselves.

Used by HrContact.py's PRIMARY path, right after LinkedInSearch finds a
name -- this is what turns "we found an HR person's LinkedIn profile"
into an actual email address to draft a message to.

Returns {"email": str} when Hunter is reasonably confident, or None if
no Hunter API key is configured, the name couldn't be split sensibly,
nothing confident came back, or the request failed.
"""
from typing import Optional

import requests

from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("enrichment.EmailGuesser")

_EMAIL_FINDER_URL = "https://api.hunter.io/v2/email-finder"
_MIN_CONFIDENCE_SCORE = 50
_REQUEST_TIMEOUT_SECONDS = 10


def split_name(full_name: str):
    """
    Naive first/last split -- good enough for typical "First Last"
    LinkedIn result titles. Middle names, suffixes (Jr., PhD) or
    single-word names can throw this off; Hunter's Email Finder simply
    returns no confident match in that case rather than a wrong one.
    """
    parts = [p for p in full_name.strip().split() if p]
    if len(parts) < 2:
        return None, None
    return parts[0], parts[-1]


def find_verified_email(full_name: str, company_domain: str):
    if not Configuration.HUNTER_API_KEY:
        log.debug("Email Finder skipped for '%s' -- no Hunter.io API key configured.", full_name)
        return None

    first_name, last_name = split_name(full_name)
    if not first_name or not last_name:
        log.debug("Could not split '%s' into first/last name -- skipping Email Finder.", full_name)
        return None

    try:
        response = requests.get(
            _EMAIL_FINDER_URL,
            params={
                "domain": company_domain,
                "first_name": first_name,
                "last_name": last_name,
                "api_key": Configuration.HUNTER_API_KEY,
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log.warning("Email Finder request failed for '%s' @ '%s': %s", full_name, company_domain, exc)
        return None

    try:
        if response.status_code == 401:
            log.error("Hunter.io rejected the configured API key (401) -- check hunter_api_key in config.ini.")
            return None
        if response.status_code == 429:
            log.warning("Hunter.io rate-limited this Email Finder lookup for '%s'.", full_name)
            return None
        response.raise_for_status()

        data = response.json().get("data") or {}
        email = data.get("email")
        score = data.get("score")
        verification_status = (data.get("verification") or {}).get("status")

        if not email:
            log.info("Email Finder had no result for '%s' @ '%s'.", full_name, company_domain)
            return None
        if verification_status == "invalid":
            log.info("Email Finder's guess for '%s' @ '%s' was flagged invalid -- discarding.", full_name, company_domain)
            return None
        if score is not None and score < _MIN_CONFIDENCE_SCORE:
            log.info("Email Finder's guess for '%s' @ '%s' had low confidence (score=%s) -- discarding.", full_name, company_domain, score)
            return None

        log.info("Email Finder produced a confident email for '%s' @ '%s' (score=%s).", full_name, company_domain, score)
        return {"email": email}

    except Exception as exc:
        log.error("Unexpected error parsing Email Finder response for '%s' @ '%s': %s", full_name, company_domain, exc)
        return None
