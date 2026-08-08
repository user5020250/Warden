"""
Shared notification helper.

Every action in the bot that is supposed to (a) DM the affected member,
(b) record itself in the action log, and/or (c) post a summary to the
guild's configured log channel goes through this one function so the
three stay in sync — nothing gets DM'd without being logged, and nothing
gets logged without being available in the log channel.
"""

import discord

from database import get_guild_config, log_action
from utils.embeds import build_embed


async def notify_and_log(
    guild: discord.Guild,
    *,
    action: str,
    user_id: int | None = None,
    moderator_id: int | None = None,
    case_id: int | None = None,
    detail: str | None = None,
    dm_target: discord.abc.User | None = None,
    dm_title: str | None = None,
    dm_description: str | None = None,
    dm_fields: list[tuple[str, str, bool]] | None = None,
    log_title: str | None = None,
    log_fields: list[tuple[str, str, bool]] | None = None,
    cfg=None,
) -> None:
    """
    Records `action` in the database action log, then (respecting the
    guild's configuration) DMs `dm_target` and posts to the log channel.
    Both notification steps are best-effort: a closed DM or a missing/
    inaccessible log channel is silently skipped, the action is still
    recorded either way.
    """
    if cfg is None:
        cfg = await get_guild_config(guild.id)

    await log_action(guild.id, action, user_id=user_id, moderator_id=moderator_id,
                      case_id=case_id, detail=detail)

    if dm_target is not None and dm_title and cfg["dm_notifications"]:
        try:
            await dm_target.send(embed=build_embed(dm_title, dm_description, dm_fields))
        except discord.Forbidden:
            pass

    if log_title and cfg["log_channel_id"]:
        log_channel = guild.get_channel(cfg["log_channel_id"])
        if log_channel is not None:
            try:
                await log_channel.send(embed=build_embed(log_title, None, fields=log_fields))
            except discord.Forbidden:
                pass
