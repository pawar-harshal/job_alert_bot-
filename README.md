# job_alert_bot

Finds relevant job openings and pushes them to Telegram as a single digest per run, so applications can be made manually — via the platform, the company's own career page, or a drafted email to an HR contact.

Structure mirrors [TicketPilot](https://github.com/pawar-harshal) — same `ConfigReader`/`Configuration`/`Logger` split, same PascalCase module naming, same file-only rotating log, same exception-handling shape (narrow/expected exceptions logged at `warning` and handled; a final `except Exception` logged at `error`; one bad item never kills the whole run).

Full design: see the project's design document (shared separately).

## What's working now

- Sources LinkedIn + Indeed via `python-jobspy`, across an expanded list of search terms (generic SDE/full-stack titles, AI/RAG/Agentic titles, stack-specific titles)
- Proactive broad web search (`sourcing/ProactiveSearch.py`) for postings outside LinkedIn/Indeed/Naukri — self-throttled to protect the shared Google search quota
- Filters every result: Mumbai-area or remote, ≤3 years experience (or unspecified), matches the configured skill set, hard-excludes .NET/C++/C#
- Dedupes against a local SQLite file, including within a single run (a job matching two search terms isn't alerted twice)
- Per-job company career-page matching (`enrichment/CareerPageFinder.py`) — best effort, links the digest straight to the company's own listing when found
- HR/recruiter contact lookup (`enrichment/HrContact.py`) — LinkedIn X-ray search + email verification primary, Hunter.io/Apollo.io domain search backup, a free `hr@domain` guess as the always-available floor; every company cached so each is only looked up once ever
- Sends one Telegram digest message per run (splits only if it would exceed Telegram's message length limit)
- Interactive `/mail <number>` Telegram command (`telegram/Commands.py`) — drafts a tailored outreach email (via LLM, `email_drafting/Draft.py`) for any digest job, with its HR contact, for you to review and send yourself
- File-only logging (`job_alert_bot/logs/job_alert_bot.log`) — nothing prints to the terminal on a normal run

## Optional API keys (all work fine left blank — each feature just degrades cleanly)

Set any of these in `config.ini`'s `[ENVIRONMENT]` section when you have them:
- `llm_api_key` — already set (reuses TicketPilot's OpenRouter key) — powers `Draft.py`
- `hunter_api_key` / `apollo_api_key` — HR-contact backup sources
- `google_search_api_key` + `google_search_engine_id` — powers the LinkedIn search, `ProactiveSearch.py`, and `CareerPageFinder.py` (all three share one free 100-queries/day quota)

## Running the two long-lived pieces on the VM

```bash
# The main cron job (every 20-30 min) -- see below
python -m job_alert_bot.JobAlertBot

# The /mail command listener -- run as its OWN separate, continuously-running
# process (systemd/screen/tmux), NOT via cron -- it needs to stay listening.
python -m job_alert_bot.telegram.Commands
```

## Architecture

```
job_alert_bot/
├── job_alert_bot/
│   ├── JobAlertBot.py        # entrypoint
│   ├── utils/
│   │   ├── ConfigReader.py    # thin configparser wrapper
│   │   ├── Configuration.py   # typed constants, GENERAL/ENVIRONMENT split
│   │   └── Logger.py          # file-only rotating logger
│   ├── data/config.ini        # gitignored -- create this yourself (see below)
│   ├── sourcing/               # JobspySource.py, ProactiveSearch.py
│   ├── filtering/               # Location.py, Experience.py, Stack.py
│   ├── dedupe/Store.py          # SQLite dedupe (in-run + persistent)
│   ├── enrichment/               # CareerPageFinder.py, HrContact.py + its Hunter/Apollo/
│   │                             # LinkedIn/EmailGuesser/ContactCache providers
│   ├── telegram/                  # Digest.py, Commands.py, MailMapping.py
│   ├── utils/LlmClient.py         # shared OpenAI-compatible LLM call (retry/logging)
│   └── email_drafting/Draft.py
├── setup.py
└── .gitignore
```

## Setup

`config.ini` is gitignored (it holds the live Telegram bot token) — after cloning, create `job_alert_bot/data/config.ini` yourself with real values. See `utils/Configuration.py` for every key it expects, split into `[GENERAL]` (behaviour/algorithm settings, same on any machine) and `[ENVIRONMENT]` (secrets and machine-specific values — each one can also be set as an OS environment variable of the same name to override the file).

```bash
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -e .
python -m job_alert_bot.JobAlertBot
```

Check `job_alert_bot/logs/job_alert_bot.log` to see what happened — logging is file-only, nothing prints to the terminal.

## Running on a schedule (VM, via cron)

```
*/25 * * * * /home/<user>/job_alert_bot/venv/bin/python -m job_alert_bot.JobAlertBot
```

---

Built as a personal project by [Harshal Pawar](https://github.com/pawar-harshal).
