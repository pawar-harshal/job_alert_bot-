"""
Tailored email drafting for a specific job + HR contact.

Builds one user-message from the job's title/company/description and
calls the shared LLM client (utils/LlmClient.py) with the fixed system
prompt in data/prompts/email_draft_prompt.txt. The model is asked for a
fixed "SUBJECT: ... / BODY: ..." format, which is parsed back into a
dict here.

This never sends anything itself -- the caller (eventually
telegram/Commands.py) is responsible for showing the result to the user
so they can review, edit, and send it manually via Gmail with their
resume attached.

Returns {"subject": str, "body": str} on success, or None if drafting
isn't possible right now (no LLM key configured, or the call failed) --
callers should treat None as "couldn't draft this one, try again later"
and never crash on it.
"""
from job_alert_bot.utils import Configuration
from job_alert_bot.utils.LlmClient import LlmNotConfigured, call_llm
from job_alert_bot.utils.Logger import get_logger

log = get_logger("email_drafting.Draft")


def _build_user_message(job: dict, hr_contact: str) -> str:
    title = job.get("title", "the role")
    company = job.get("company", "the company")
    location = job.get("location", "")
    description = (job.get("description") or "").strip()
    # Descriptions can be very long -- keep the prompt focused and cheap.
    if len(description) > 4000:
        description = description[:4000] + "..."

    lines = [
        f"Role: {title}",
        f"Company: {company}",
    ]
    if location:
        lines.append(f"Location: {location}")
    if hr_contact:
        lines.append(f"HR/recruiter contact this will be sent to: {hr_contact}")
    if description:
        lines.append("")
        lines.append("Job description:")
        lines.append(description)
    else:
        lines.append("")
        lines.append("(No job description text was available -- draft from the role and company name alone, staying general about fit rather than inventing requirements.)")

    return "\n".join(lines)


def _parse_response(text: str):
    if not text or "SUBJECT:" not in text or "BODY:" not in text:
        log.warning("LLM response didn't match the expected SUBJECT/BODY format, discarding: %r", text[:200] if text else text)
        return None

    try:
        head, body = text.split("BODY:", 1)
        subject = head.split("SUBJECT:", 1)[1].strip()
        body = body.strip()
        if not subject or not body:
            log.warning("Parsed an empty subject or body from the LLM response, discarding.")
            return None
        return {"subject": subject, "body": body}
    except Exception as exc:
        log.warning("Failed to parse SUBJECT/BODY out of LLM response: %s", exc)
        return None


def draft_email(job: dict, hr_contact: str = ""):
    company = job.get("company", "")
    title = job.get("title", "")

    try:
        messages = [
            {"role": "system", "content": Configuration.EMAIL_DRAFT_PROMPT},
            {"role": "user", "content": _build_user_message(job, hr_contact)},
        ]
        raw = call_llm(messages)
    except LlmNotConfigured:
        log.warning("Email drafting skipped for '%s' @ '%s' -- no LLM API key configured yet.", title, company)
        return None
    except Exception as exc:
        log.error("Email drafting failed for '%s' @ '%s': %s", title, company, exc)
        return None

    drafted = _parse_response(raw)
    if drafted is None:
        log.error("Email drafting produced an unusable response for '%s' @ '%s'.", title, company)
        return None

    log.info("Drafted email for '%s' @ '%s'.", title, company)
    return drafted
