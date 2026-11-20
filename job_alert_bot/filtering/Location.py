"""Location filter: Mumbai/Navi Mumbai/Thane-area, or fully remote."""
from job_alert_bot.utils import Configuration


def is_remote(row: dict) -> bool:
    if row.get("is_remote") is True:
        return True
    text = f"{row.get('location') or ''} {row.get('title') or ''} {row.get('job_type') or ''}".lower()
    return "remote" in text or "work from home" in text or "wfh" in text


def passes(row: dict) -> bool:
    if is_remote(row):
        return True
    loc = (row.get("location") or "").lower()
    return any(kw in loc for kw in Configuration.MUMBAI_AREA_KEYWORDS)
