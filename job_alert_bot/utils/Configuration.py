"""
Reads config.ini ONCE at import time and converts every value to its
proper type ONCE, exposing plain module-level constants.

Every other file in the codebase imports THIS module and uses its
constants directly (e.g. Configuration.TELEGRAM_BOT_TOKEN) -- nothing
else calls ConfigReader directly or repeats a type conversion. Same
pattern as TicketPilot's Configuration.py.

ENVIRONMENT values additionally check an OS environment variable of the
SAME name first, falling back to config.ini only if that variable isn't
set -- this is what lets a deploy-time secret (e.g. the Telegram bot
token) be overridden without ever being committed in config.ini. GENERAL
values are never overridden this way -- same split as TicketPilot.
"""
import os

from job_alert_bot.utils import ConfigReader
from job_alert_bot.utils.Logger import get_logger

log = get_logger("utils.Configuration")

try:
    GENERAL = ConfigReader.get_section("GENERAL")
    ENVIRONMENT = ConfigReader.get_section("ENVIRONMENT")

    # -----------------------------------------------------------------
    # GENERAL -- behaviour/algorithm settings, the same on any machine.
    # File-only, never overridden by an environment variable.
    # -----------------------------------------------------------------
    def _csv(raw: str) -> list:
        """Splits a comma/newline-separated config value into a clean list."""
        return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]

    SEARCH_TERMS = _csv(GENERAL["search_terms"])
    SITE_NAMES = _csv(GENERAL["site_names"])
    LOCATION = str(GENERAL["location"])
    COUNTRY_INDEED = str(GENERAL["country_indeed"])
    HOURS_OLD = int(GENERAL["hours_old"])
    RESULTS_WANTED = int(GENERAL["results_wanted"])
    DELAY_BETWEEN_SEARCHES = int(GENERAL["delay_between_searches_seconds"])
    FETCH_FULL_DESCRIPTION = GENERAL["fetch_full_description"].strip().lower() == "true"

    MAX_EXPERIENCE_YEARS = int(GENERAL["max_experience_years"])
    MUMBAI_AREA_KEYWORDS = _csv(GENERAL["mumbai_area_keywords"])
    CORE_STACK_KEYWORDS = _csv(GENERAL["core_stack_keywords"])
    ADAPTABLE_STACK_KEYWORDS = _csv(GENERAL["adaptable_stack_keywords"])
    ALL_INCLUDE_KEYWORDS = CORE_STACK_KEYWORDS + ADAPTABLE_STACK_KEYWORDS
    EXCLUDE_STACK_KEYWORDS = _csv(GENERAL["exclude_stack_keywords"])

    LOGGING_LEVEL = str(GENERAL["logging_level"])

    # LLM used for email drafting (and later, career-page matching).
    # Behaviour/retry settings -- same on any machine, so GENERAL.
    LLM_MODEL = str(GENERAL["llm_model"])
    LLM_BASE_URL = str(GENERAL["llm_base_url"])
    LLM_RETRY_ATTEMPTS = int(GENERAL["llm_retry_attempts"])
    LLM_RETRY_WAIT_MULTIPLIER_MS = int(GENERAL["llm_retry_wait_multiplier_ms"])
    LLM_RETRY_MAX_WAIT_MS = int(GENERAL["llm_retry_max_wait_ms"])

    # How many of the most recent digest's jobs /mail <number> can still
    # refer to -- keeps the number->job mapping file from growing forever.
    MAIL_COMMAND_HISTORY_RUNS = int(GENERAL["mail_command_history_runs"])

    # How often (hours) ProactiveSearch is allowed to actually run its
    # broad web search, to protect the shared Google search quota.
    PROACTIVE_SEARCH_INTERVAL_HOURS = int(GENERAL["proactive_search_interval_hours"])

    # Prompt text used for LLM-drafted outreach emails, loaded once here
    # (same pattern TicketPilot uses for its system_prompt.txt).
    _PACKAGE_ROOT_FOR_PROMPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _EMAIL_DRAFT_PROMPT_PATH = os.path.join(_PACKAGE_ROOT_FOR_PROMPTS, "data", "prompts", "email_draft_prompt.txt")
    with open(_EMAIL_DRAFT_PROMPT_PATH, "r", encoding="utf-8") as _f:
        EMAIL_DRAFT_PROMPT = _f.read().strip()

    # -----------------------------------------------------------------
    # ENVIRONMENT -- this machine/deployment's own settings and secrets.
    # Each one checks os.environ[SAME_NAME] first, falls back to
    # config.ini if that variable isn't set.
    # -----------------------------------------------------------------
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", ENVIRONMENT["telegram_bot_token"])
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", ENVIRONMENT["telegram_chat_id"])

    # Secret -- may be blank until the user has an OpenRouter/LLM key for
    # this project specifically. Blank means Draft.py returns cleanly
    # with "not available" instead of erroring.
    LLM_API_KEY = os.environ.get("LLM_API_KEY", ENVIRONMENT.get("llm_api_key", "")).strip()

    # Secret -- may be blank until the user has a Hunter.io account.
    # Blank means HrContact.py returns cleanly with "not found" instead
    # of erroring.
    HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", ENVIRONMENT.get("hunter_api_key", "")).strip()

    # Secret -- backup HR-contact lookup source, tried after the primary
    # LinkedIn-search path. May also be blank.
    APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", ENVIRONMENT.get("apollo_api_key", "")).strip()

    # Secrets -- PRIMARY HR-contact path (LinkedIn X-ray search via
    # Google). Both may be blank, in which case that path is skipped.
    GOOGLE_SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY", ENVIRONMENT.get("google_search_api_key", "")).strip()
    GOOGLE_SEARCH_ENGINE_ID = os.environ.get("GOOGLE_SEARCH_ENGINE_ID", ENVIRONMENT.get("google_search_engine_id", "")).strip()

    _dedupe_db_raw = os.environ.get("DEDUPE_DB_PATH", ENVIRONMENT.get("dedupe_db_path", "")).strip()
    if _dedupe_db_raw:
        DEDUPE_DB_PATH = _dedupe_db_raw
    else:
        # Default: job_alert_bot/data/job_alert.db, sibling to config.ini.
        _PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        DEDUPE_DB_PATH = os.path.join(_PACKAGE_ROOT, "data", "job_alert.db")

    _contact_cache_db_raw = os.environ.get("CONTACT_CACHE_DB_PATH", ENVIRONMENT.get("contact_cache_db_path", "")).strip()
    if _contact_cache_db_raw:
        CONTACT_CACHE_DB_PATH = _contact_cache_db_raw
    else:
        # Default: job_alert_bot/data/hr_contacts.db, sibling to config.ini.
        _PACKAGE_ROOT_FOR_CACHE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        CONTACT_CACHE_DB_PATH = os.path.join(_PACKAGE_ROOT_FOR_CACHE, "data", "hr_contacts.db")

    _mail_mapping_raw = os.environ.get("MAIL_MAPPING_PATH", ENVIRONMENT.get("mail_mapping_path", "")).strip()
    if _mail_mapping_raw:
        MAIL_MAPPING_PATH = _mail_mapping_raw
    else:
        # Default: job_alert_bot/data/mail_mapping.json, sibling to config.ini.
        _PACKAGE_ROOT_FOR_MAPPING = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        MAIL_MAPPING_PATH = os.path.join(_PACKAGE_ROOT_FOR_MAPPING, "data", "mail_mapping.json")

    log.info("Configuration loaded successfully from config.ini (with any env-var overrides applied).")

except KeyError as exc:
    log.error("Configuration is missing a required key: %s", exc)
    raise
except Exception as exc:
    log.error("Unexpected error while loading configuration: %s", exc)
    raise
