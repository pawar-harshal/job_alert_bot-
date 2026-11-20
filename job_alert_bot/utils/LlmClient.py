"""
Shared, low-level LLM call -- the ONLY place in the codebase that talks
to the OpenAI-compatible client directly. Callers (Draft.py, and later
career-page matching) pass plain chat messages and get back the model's
reply text.

Same shape as TicketPilot's AgentOrchestrator.call_llm: a RateLimitError
is expected/recoverable (logged at warning, retried automatically by the
@retry decorator), anything else is unexpected (logged at error, raised
to the caller). No tool-calling here -- this project only needs plain
drafting/matching completions, not agentic tool use.
"""
from openai import OpenAI, RateLimitError
from retrying import retry

from job_alert_bot.utils import Configuration
from job_alert_bot.utils.Logger import get_logger

log = get_logger("utils.LlmClient")


def _is_retryable_llm_error(exc: BaseException) -> bool:
    return isinstance(exc, RateLimitError)


class LlmNotConfigured(Exception):
    """Raised when no LLM API key is configured yet -- callers should
    catch this and fall back to a clean "not available" result rather
    than letting it surface as an unexpected error."""


@retry(
    stop_max_attempt_number=Configuration.LLM_RETRY_ATTEMPTS,
    wait_exponential_multiplier=Configuration.LLM_RETRY_WAIT_MULTIPLIER_MS,
    wait_exponential_max=Configuration.LLM_RETRY_MAX_WAIT_MS,
    retry_on_exception=_is_retryable_llm_error,
)
def call_llm(messages: list) -> str:
    if not Configuration.LLM_API_KEY:
        raise LlmNotConfigured("No LLM_API_KEY configured -- set llm_api_key in config.ini or the LLM_API_KEY env var.")

    try:
        client = OpenAI(base_url=Configuration.LLM_BASE_URL, api_key=Configuration.LLM_API_KEY)
        log.debug("Calling LLM model=%s via %s", Configuration.LLM_MODEL, Configuration.LLM_BASE_URL)
        response = client.chat.completions.create(model=Configuration.LLM_MODEL, messages=messages)
        return response.choices[0].message.content
    except RateLimitError as exc:
        log.warning("LLM call rate-limited, will retry if attempts remain: %s", exc)
        raise
    except Exception as exc:
        log.error("LLM call failed: %s", exc)
        raise
