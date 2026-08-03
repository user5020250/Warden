"""
Shared embed builder. Every embed in the bot goes through this so the
styling (black, no emojis, consistent footer) stays uniform.
"""

import discord
from datetime import datetime, timezone

from config import EMBED_COLOR


def build_embed(title: str, description: str = None, fields: list[tuple[str, str, bool]] = None) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed


def error_embed(message: str) -> discord.Embed:
    return build_embed("Error", message)


def success_embed(title: str, description: str = None, fields=None) -> discord.Embed:
    return build_embed(title, description, fields)


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
