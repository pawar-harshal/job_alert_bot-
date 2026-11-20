"""
HR/recruiter contact lookup -- the public entry point callers use.

Orchestrates, in order, for a given company:
    1. ContactCache -- has this domain already been looked up before?
       If so, return that cached result and never call any API again
       for this company.
    2. PRIMARY -- LinkedInSearch finds the HR/recruiter's public
       LinkedIn profile via an X-ray search (Google search index only,
       never touches LinkedIn itself); if it finds a name, EmailGuesser
       asks Hunter.io's Email Finder to turn that name + domain into a
       verified email.
    3. BACKUP -- if the primary path found nothing (no search API
       configured, no profile found, or no confident email for that
       person), fall through to HunterContact's domain search, then
       ApolloContact, in that order.
    4. A labelled hr@domain guess (generic, never person-name-based) --
       if nothing above found
       anything, this is returned UNVERIFIED rather than as a confirmed
       contact.
Whatever is found (or guessed) is cached, so step 1 is a hit for every
future job at that same company -- this is what makes the free API
quotas last, since they're spent once per company rather than once per
job.

Returns, on success: {"email": str, "verified": bool, "source": str,
"profile_url": str|None} where source is "linkedin", "hunter",
"apollo", "guess", or "cache". profile_url is only set when the
primary (LinkedIn) path is what found the contact. Returns None only
when no company domain was available to look anything up with at all.
"""
from typing import Optional
from urllib.parse import urlparse

from job_alert_bot.enrichment import ApolloContact, EmailGuesser, HunterContact, LinkedInSearch
from job_alert_bot.enrichment.ContactCache import ContactCache
from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("enrichment.HrContact")


def domain_from_url(url: Optional[str]) -> Optional[str]:
    """
    Pulls a bare domain (e.g. "acme.com") out of a company/career-page
    URL such as the "company_url" field jobspy sometimes returns. Used
    by callers that have a job row but no domain field of their own.
    """
    if not url:
        return None
    try:
        netloc = urlparse(url if "://" in url else f"https://{url}").netloc
        return netloc[4:] if netloc.startswith("www.") else netloc or None
    except Exception as exc:
        log.warning("Could not parse a domain out of URL '%s': %s", url, exc)
        return None


# Job platforms themselves, never a real employer's domain. jobspy's
# "company_url" field is frequently the PLATFORM's own company profile
# page (e.g. LinkedIn's "nl.linkedin.com/company/acme") rather than the
# employer's actual website -- guessing an email at one of these would
# produce nonsense like "hr@nl.linkedin.com". Checked with endswith so
# any regional subdomain (nl., de., in., ...) is caught too.
_JOB_PLATFORM_DOMAINS = (
    "linkedin.com", "indeed.com", "naukri.com", "glassdoor.com",
    "ziprecruiter.com", "bayt.com",
)


def _is_job_platform_domain(domain: str) -> bool:
    domain = domain.lower()
    return any(domain == d or domain.endswith(f".{d}") for d in _JOB_PLATFORM_DOMAINS)


def domain_from_row(row: dict) -> Optional[str]:
    """
    Pulls the company's REAL domain out of a jobspy row -- the entry
    point callers with a job row (not just a bare URL) should use
    instead of domain_from_url() directly. Prefers "company_url_direct"
    (jobspy's field for the employer's own external site, when it found
    one) over "company_url" (often just the platform's own company
    profile page -- see _JOB_PLATFORM_DOMAINS above). Either field
    resolving to a known job-platform domain is treated the same as it
    being missing, rather than trusted as the employer's domain.
    """
    for key in ("company_url_direct", "company_url"):
        domain = domain_from_url(row.get(key))
        if domain and not _is_job_platform_domain(domain):
            return domain
    return None


def find_hr_contact(company: str, company_domain: Optional[str] = None):
    if not company_domain:
        log.debug("HR contact lookup skipped for '%s' -- no company domain available to look up.", company)
        return None

    cache = ContactCache(Configuration.CONTACT_CACHE_DB_PATH)
    try:
        cached = cache.get(company_domain)
        if cached is not None:
            log.debug("HR contact for '%s' served from cache (source=%s).", company, cached.get("source"))
            return cached

        # -- PRIMARY: LinkedIn X-ray search -> Hunter Email Finder -----
        profile = LinkedInSearch.find_hr_profile(company, company_domain)
        if profile is not None:
            verified_email = EmailGuesser.find_verified_email(profile["name"], company_domain)
            if verified_email is not None:
                result = {
                    "email": verified_email["email"],
                    "verified": True,
                    "source": "linkedin",
                    "profile_url": profile["profile_url"],
                }
                cache.set(company_domain, result["email"], result["verified"], result["source"], result["profile_url"])
                return result
            log.info(
                "Found a LinkedIn profile for '%s' (%s) but Email Finder had no confident email -- falling back.",
                company, profile["name"],
            )

        # -- BACKUP: Hunter.io domain search, then Apollo.io -----------
        hunter_result = HunterContact.find_contact(company_domain)
        if hunter_result is not None:
            result = {"email": hunter_result["email"], "verified": True, "source": "hunter", "profile_url": None}
            cache.set(company_domain, result["email"], result["verified"], result["source"])
            return result

        apollo_result = ApolloContact.find_contact(company_domain)
        if apollo_result is not None:
            result = {"email": apollo_result["email"], "verified": True, "source": "apollo", "profile_url": None}
            cache.set(company_domain, result["email"], result["verified"], result["source"])
            return result

        # Nothing above found a real, confirmed contact -- fall back to
        # a generic hr@domain guess rather than nothing. Deliberately
        # NOT a person-name-based guess (e.g. firstname.lastname@domain)
        # -- a generic HR mailbox is far more likely to actually exist
        # and be monitored than a guessed pattern for one specific
        # person, and it's never embarrassingly wrong about who someone
        # is. Still cached, so we don't keep re-asking every provider
        # about a company that has nothing.
        guess_email = f"hr@{company_domain}"
        result = {"email": guess_email, "verified": False, "source": "guess", "profile_url": None}
        cache.set(company_domain, result["email"], result["verified"], result["source"])
        log.info("No confirmed HR contact for '%s' -- using unverified guess %s.", company, guess_email)
        return result

    finally:
        cache.close()
