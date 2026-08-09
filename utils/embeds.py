"""
Shared embed builder. Every embed in the bot goes through this so the
styling (black, no emojis, bold field names, consistent footer and
timestamp) stays uniform across every command.
"""

import discord
from datetime import datetime, timezone

from config import EMBED_COLOR

# Shown on the bottom of every embed the bot sends, so DMs, log entries, and
# in-server replies all read as coming from the same system rather than a
# collection of ad-hoc messages.
FOOTER_TEXT = "Warden \u2022 Moderation System"


def build_embed(
    title: str,
    description: str = None,
    fields: list[tuple[str, str, bool]] = None,
    footer: str | None = FOOTER_TEXT,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=f"**{name}**", value=value, inline=inline)
    if footer:
        embed.set_footer(text=footer)
    return embed


def error_embed(message: str) -> discord.Embed:
    return build_embed("Unable to Complete Request", message)


def success_embed(title: str, description: str = None, fields=None) -> discord.Embed:
    return build_embed(title, description, fields)


def code(value) -> str:
    """Wraps a value in backticks for consistent inline formatting."""
    return f"`{value}`"


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "Permanent"
    if seconds <= 0:
        return "Expired"
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)
