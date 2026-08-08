"""
Global configuration constants for the Jail System bot.
"""

import os

# ---------------------------------------------------------------------------
# Embed styling
# ---------------------------------------------------------------------------
# All embeds across the bot use pure black, per spec. No emojis anywhere.
EMBED_COLOR = 0x000000

# On Railway (and most PaaS hosts), the container filesystem is rebuilt from
# scratch on every deploy — anything written to a plain relative path like
# "jail.db" is gone after the next update. Set the DB_PATH environment
# variable to a path inside an attached persistent Volume (e.g. /data/jail.db)
# so the database survives redeploys. Falls back to a local file for
# development, where a fresh working directory isn't an issue.
DB_PATH = os.getenv("DB_PATH", "jail.db")

# Default sentence length (minutes) used when a guild has not configured one.
DEFAULT_JAIL_MINUTES = 60

# How often (seconds) the background task checks for expired sentences.
SENTENCE_CHECK_INTERVAL = 30

# How often (seconds) probation monitoring is swept.
PROBATION_CHECK_INTERVAL = 60
