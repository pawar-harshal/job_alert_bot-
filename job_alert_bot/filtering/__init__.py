"""
Runs every filter in order and gives one verdict per job.
Each individual filter lives in its own module (Location.py,
Experience.py, Stack.py) so any one of them can be changed or tested
without touching the others.
"""
from job_alert_bot.filtering import Experience, Location, Stack
from job_alert_bot.utils.Logger import get_logger

log = get_logger("filtering")


def should_alert(row: dict):
    """
    Runs all filters against one job (a plain dict, as yielded by a
    sourcing module). Returns (passes: bool, reason: str, experience_note: str).

    reason is a short human-readable string -- used both for the debug
    log and, when passes=True, folded into the Telegram alert text.
    experience_note is always returned on a pass, even when empty.
    """
    if not Location.passes(row):
        return False, "location not in Mumbai area / not remote", ""

    stack_ok, stack_reason = Stack.passes(row)
    if not stack_ok:
        return False, stack_reason, ""

    exp_ok, exp_note = Experience.passes(row)
    if not exp_ok:
        return False, exp_note, ""

    return True, stack_reason, exp_note
