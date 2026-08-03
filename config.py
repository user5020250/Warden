"""
Global configuration constants for the Jail System bot.
"""

# ---------------------------------------------------------------------------
# Embed styling
# ---------------------------------------------------------------------------
# All embeds across the bot use pure black, per spec. No emojis anywhere.
EMBED_COLOR = 0x000000

DB_PATH = "jail.db"

# Default sentence length (minutes) used when a guild has not configured one.
DEFAULT_JAIL_MINUTES = 60

# How often (seconds) the background task checks for expired sentences.
SENTENCE_CHECK_INTERVAL = 30

# How often (seconds) probation monitoring is swept.
PROBATION_CHECK_INTERVAL = 60
