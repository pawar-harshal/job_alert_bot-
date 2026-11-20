"""
Stack filter: keeps a job if it mentions at least one core or adaptable
technology, and hard-drops it if it lists .NET/C++/C# as a requirement --
regardless of anything else matching.
"""
from job_alert_bot.utils import Configuration


def passes(row: dict):
    """Returns (passes: bool, reason: str)."""
    text = f"{row.get('title') or ''} {row.get('description') or ''}".lower()

    for bad in Configuration.EXCLUDE_STACK_KEYWORDS:
        if bad in text:
            return False, f"excluded stack match: '{bad.strip()}'"

    for good in Configuration.ALL_INCLUDE_KEYWORDS:
        if good in text:
            return True, f"matched: '{good}'"

    return False, "no matching stack keywords"
