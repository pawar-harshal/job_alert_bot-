"""
Title filter: drops a job outright if its TITLE matches an excluded
role keyword (e.g. "Senior", "Data Scientist", "DevOps") -- checked
against the title only, never the description, so a job whose
description happens to mention something like "mentoring senior
stakeholders" isn't wrongly dropped.

This is deliberately separate from Experience.py's year-number
parsing: Experience.py only catches seniority when the description
states a number of years and that number happens to parse: a role
titled "Senior Lead Software Engineer" with no parseable years in its
text sails right through that filter. Checking the title directly
catches those too.
"""
from job_alert_bot.utils import Configuration


def passes(row: dict):
    """Returns (passes: bool, reason: str)."""
    title = (row.get("title") or "").lower()

    for bad in Configuration.EXCLUDE_TITLE_KEYWORDS:
        if bad in title:
            return False, f"excluded title match: '{bad.strip()}'"

    return True, ""
