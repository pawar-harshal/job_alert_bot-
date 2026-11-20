"""
Experience filter: keeps a job if the minimum years mentioned is <=
Configuration.MAX_EXPERIENCE_YEARS, or if no experience requirement could
be found in the description at all (kept, flagged as "not specified"
rather than silently dropped -- a missed opportunity is worse than a
borderline one).

Needs the FULL job description to work -- jobspy's default preview
snippet usually doesn't contain the experience line at all, which is why
Configuration.FETCH_FULL_DESCRIPTION exists and must be enabled.
"""
import re

from job_alert_bot.utils import Configuration

# Matches things like "4+ years", "2-4 yrs", "minimum 5 years", "3 to 6 years"
_PATTERNS = [
    re.compile(r"(\d+)\s*\+?\s*-\s*(\d+)\s*\+?\s*years?", re.IGNORECASE),
    re.compile(r"(\d+)\s*\+?\s*to\s*(\d+)\s*\+?\s*years?", re.IGNORECASE),
    re.compile(r"(?:minimum|min\.?|at least)\s*(\d+)\s*\+?\s*years?", re.IGNORECASE),
    re.compile(r"(\d+)\s*\+\s*years?", re.IGNORECASE),
    re.compile(r"(\d+)\s*-\s*(\d+)\s*\+?\s*yrs?", re.IGNORECASE),
    re.compile(r"(\d+)\s*\+?\s*years?\s*(?:of)?\s*experience", re.IGNORECASE),
]


def extract_min_years(description: str):
    """Returns the lowest 'minimum years required' number found, or None."""
    if not description:
        return None

    candidates = []
    for pattern in _PATTERNS:
        for match in pattern.finditer(description):
            groups = [g for g in match.groups() if g is not None]
            if groups:
                try:
                    candidates.append(int(groups[0]))
                except ValueError:
                    continue

    return min(candidates) if candidates else None


def passes(row: dict):
    """Returns (passes: bool, note: str)."""
    min_years = extract_min_years(row.get("description") or "")

    if min_years is None:
        return True, "experience not specified"
    if min_years <= Configuration.MAX_EXPERIENCE_YEARS:
        return True, f"~{min_years}+ yrs required"
    return False, f"~{min_years}+ yrs required (too senior)"
