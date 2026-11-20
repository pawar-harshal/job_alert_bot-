"""
Thin wrapper around Python's built-in logging module.

No custom logging package -- this just configures the stdlib logging
module once (level from config.ini) and hands back a named logger per
module, the same way logging.getLogger(__name__) is normally used.

This stays a foundational, low-level module (like ConfigReader) rather
than depending on Configuration.py -- Configuration.py is a higher-level
module and nothing foundational should import it, to avoid any risk of a
circular import between the two. (Same split as TicketPilot's Logger.py.)
"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler

from job_alert_bot.utils import ConfigReader

IS_CONFIGURED = False

# Sibling of data/ (same level as job_alert_bot/data/config.ini) --
# created on first use, not checked into the repo, so a fresh clone starts
# with no logs/ folder until the app actually runs once.
_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_PACKAGE_ROOT, "logs")
LOG_FILE_PATH = os.path.join(LOG_DIR, "job_alert_bot.log")


def configure_once() -> None:
    global IS_CONFIGURED
    if IS_CONFIGURED:
        return

    try:
        level_name = ConfigReader.get_section("GENERAL")["logging_level"]
    except (KeyError, FileNotFoundError):
        level_name = "INFO"
    level = getattr(logging, level_name.upper(), logging.INFO)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    root = logging.getLogger("job_alert_bot")
    root.setLevel(level)

    # File output ONLY -- no terminal/stdout handler. One log file that
    # rotates at midnight and keeps 14 days of history, so it doesn't grow
    # forever and old days are still around to look back at after a run
    # that behaved oddly.
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        LOG_FILE_PATH, when="midnight", backupCount=14, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    root.propagate = False

    IS_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_once()
    return logging.getLogger(f"job_alert_bot.{name}")
