import discord
from discord.ext import commands, tasks

from database import db, now
from config import SENTENCE_CHECK_INTERVAL
from utils.jail_actions import release_member


class Scheduler(commands.Cog):
    """Background loop that releases members once their timed sentence expires."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_sentences.start()

    def cog_unload(self):
        self.check_sentences.cancel()

    @tasks.loop(seconds=SENTENCE_CHECK_INTERVAL)
    async def check_sentences(self):
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE status = 'active' AND frozen = 0 AND duration_seconds IS NOT NULL"
        )
        rows = await cur.fetchall()
        current = now()
        for row in rows:
            if current - row["created_at"] < row["duration_seconds"]:
                continue
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                continue
            member = guild.get_member(row["user_id"])
            await release_member(guild, member, guild.me, row["case_id"], "expired", self.bot)

    @check_sentences.before_loop
    async def before_check_sentences(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduler(bot))
