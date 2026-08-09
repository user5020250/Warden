"""
Global configuration constants for the Warden moderation bot.
"""

import os

# ---------------------------------------------------------------------------
# Embed styling
# ---------------------------------------------------------------------------
# All embeds across the bot use pure black, per spec. No emojis anywhere.
EMBED_COLOR = 0x000000

# On Railway (and most PaaS hosts), the container filesystem is rebuilt from
# scratch on every deploy — anything written to a plain relative path like
# "warden.db" is gone after the next update. Set the DB_PATH environment
# variable to a path inside an attached persistent Volume (e.g.
# /data/warden.db) so the database survives redeploys. Falls back to a
# local file for development, where a fresh working directory isn't an
# issue.
DB_PATH = os.getenv("DB_PATH", "warden.db")

# Default sentence length (seconds) used when a guild has not configured one.
DEFAULT_JAIL_SECONDS = 3600

# How often (seconds) the background task checks for expired sentences.
SENTENCE_CHECK_INTERVAL = 30

# How often (seconds) the background task checks for expired cell visitations.
VISITATION_CHECK_INTERVAL = 60

# AutoJail defaults, used the first time a guild enables it.
DEFAULT_AUTOJAIL_THRESHOLD = 5
DEFAULT_AUTOJAIL_WINDOW_SECONDS = 60
DEFAULT_AUTOJAIL_DURATION_SECONDS = 1800

# Rows per page for paginated listings (/jailstatus, /reports, /warnings
# list, /appeals, /jailhistory, /jailsearch, /jaillogs).
PAGE_SIZE = 5
