import discord
from discord.ext import commands, tasks

from database import db, now, get_expired_visitations, close_visitation, log_action
from config import SENTENCE_CHECK_INTERVAL
from utils.embeds import build_embed
from utils.jail_actions import release_member


class Scheduler(commands.Cog):
    """Background loop that releases members once their timed sentence expires,
    and revokes cell visitation access once its granted duration is up."""

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

    @tasks.loop(seconds=SENTENCE_CHECK_INTERVAL)
    async def check_visitations(self):
        for row in await get_expired_visitations():
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                continue
            channel = guild.get_channel(row["channel_id"])
            if channel is None:
                # Channel is gone already (e.g. occupant released) - nothing left to revoke.
                await close_visitation(row["visitation_id"], status="revoked")
                continue
            try:
                await channel.set_permissions(
                    discord.Object(id=row["visitor_id"]), overwrite=None,
                    reason="Visitation access expired",
                )
            except discord.Forbidden:
                pass
            await close_visitation(row["visitation_id"], status="expired")
            await log_action(
                row["guild_id"], "visitation_expired", user_id=row["occupant_id"],
                case_id=row["case_id"], detail=f"Visitor {row['visitor_id']}'s access to cell expired",
            )
            try:
                visitor = guild.get_member(row["visitor_id"])
                if visitor is not None:
                    await visitor.send(embed=build_embed(
                        "Your Visitation Access Has Expired",
                        f"Your temporary access to {channel.mention if channel else 'the jail cell'} "
                        "has ended.",
                    ))
            except discord.Forbidden:
                pass

    @check_visitations.before_loop
    async def before_check_visitations(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduler(bot))
