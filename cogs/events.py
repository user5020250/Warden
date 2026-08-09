"""
AutoJail works by watching message timestamps per member: if a member
sends `autojail_threshold` or more messages within a rolling
`autojail_window_seconds` window, that rate itself counts as the
violation and the member is jailed automatically. Tracking is kept in
memory (per-process) rather than the database, since it only needs to
survive a few seconds/minutes and doesn't need to persist across restarts.
"""

import time
import discord
from discord.ext import commands

from database import db, get_guild_config, clear_dead_cell_channel
from utils.embeds import build_embed, format_duration
from utils.notify import notify_and_log
from utils.permissions import is_staff
from utils.jail_actions import jail_member


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (guild_id, user_id) -> list[timestamp]
        self._message_log: dict[tuple[int, int], list[float]] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.author, discord.Member) or is_staff(message.author):
            return

        cfg = await get_guild_config(message.guild.id)
        if not cfg["autojail_enabled"]:
            return

        cur = await db().execute(
            "SELECT 1 FROM autojail_whitelist WHERE guild_id = ? AND user_id = ?",
            (message.guild.id, message.author.id),
        )
        if await cur.fetchone():
            return

        cur = await db().execute(
            "SELECT 1 FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active'",
            (message.guild.id, message.author.id),
        )
        if await cur.fetchone():
            return

        key = (message.guild.id, message.author.id)
        window = cfg["autojail_window_seconds"]
        now_ts = time.monotonic()
        history = [t for t in self._message_log.get(key, []) if now_ts - t <= window]
        history.append(now_ts)
        self._message_log[key] = history

        if len(history) < cfg["autojail_threshold"]:
            return

        self._message_log.pop(key, None)

        success, _, case_id = await jail_member(
            message.guild, message.author, self.bot.user,
            f"AutoJail: sent {len(history)} messages within {format_duration(window)}",
            cfg["autojail_duration_seconds"],
        )
        if not success:
            return

        await notify_and_log(
            message.guild, action="autojail", user_id=message.author.id, case_id=case_id,
            detail=f"{len(history)} messages within {format_duration(window)}",
            dm_target=message.author, dm_title="You Have Been Automatically Jailed",
            dm_fields=[
                ("Server", message.guild.name, True),
                ("Case ID", f"`#{case_id}`", True),
                ("Duration", f"`{format_duration(cfg['autojail_duration_seconds'])}`", True),
                ("Reason", "Sent messages faster than this server's configured rate limit.", False),
            ],
            log_title="AutoJail Triggered",
            log_fields=[
                ("Member", f"{message.author.mention} (`{message.author.id}`)", True),
                ("Case ID", f"`#{case_id}`", True),
                ("Messages", f"`{len(history)}` in `{format_duration(window)}`", True),
            ],
            cfg=cfg,
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if isinstance(channel, discord.TextChannel):
            await clear_dead_cell_channel(channel.guild.id, channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
