import discord
from discord.ext import commands, tasks

from config import SENTENCE_CHECK_INTERVAL, VISITATION_CHECK_INTERVAL
from database import db, now, get_expired_visitations, close_visitation
from utils.jail_actions import release_member
from utils.notify import notify_and_log


class Scheduler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_sentences.start()
        self.check_visitations.start()

    def cog_unload(self):
        self.check_sentences.cancel()
        self.check_visitations.cancel()

    @tasks.loop(seconds=SENTENCE_CHECK_INTERVAL)
    async def check_sentences(self):
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE status = 'active' AND duration_seconds IS NOT NULL"
        )
        cases = await cur.fetchall()
        for case in cases:
            if case["created_at"] + case["duration_seconds"] > now():
                continue
            guild = self.bot.get_guild(case["guild_id"])
            if guild is None:
                continue
            member = guild.get_member(case["user_id"])
            success, _ = await release_member(guild, member, self.bot.user, case["case_id"], "expired")
            if not success:
                continue
            await notify_and_log(
                guild, action="sentence_expired", user_id=case["user_id"], case_id=case["case_id"],
                dm_target=member, dm_title="Your Sentence Has Ended",
                dm_fields=[("Server", guild.name, True), ("Case ID", f"`#{case['case_id']}`", True)],
                log_title="Sentence Expired",
                log_fields=[
                    ("Member", f"<@{case['user_id']}> (`{case['user_id']}`)", True),
                    ("Case ID", f"`#{case['case_id']}`", True),
                ],
            )

    @tasks.loop(seconds=VISITATION_CHECK_INTERVAL)
    async def check_visitations(self):
        for visitation in await get_expired_visitations():
            guild = self.bot.get_guild(visitation["guild_id"])
            if guild is not None:
                channel = guild.get_channel(visitation["channel_id"])
                visitor = guild.get_member(visitation["visitor_id"])
                if channel is not None and visitor is not None:
                    try:
                        await channel.set_permissions(visitor, overwrite=None, reason="Visitation expired")
                    except discord.Forbidden:
                        pass
            await close_visitation(visitation["visitation_id"], "expired")

    @check_sentences.before_loop
    async def before_check_sentences(self):
        await self.bot.wait_until_ready()

    @check_visitations.before_loop
    async def before_check_visitations(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduler(bot))
