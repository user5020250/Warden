import discord
from discord import app_commands
from discord.ext import commands

from database import db, now
from utils.embeds import build_embed, format_duration
from utils.permissions import trusted_only


class Statistics(commands.Cog):
    """Reporting on jail activity. Grouped under /jailstats (see naming note in sentence.py)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    jailstats = app_commands.Group(name="jailstats", description="Jail system statistics.")

    @jailstats.command(name="overview", description="Overall statistics.")
    @trusted_only()
    async def overview(self, interaction: discord.Interaction):
        await interaction.response.defer()
        gid = interaction.guild.id
        cur = await db().execute("SELECT COUNT(*) c FROM jail_cases WHERE guild_id = ?", (gid,))
        total = (await cur.fetchone())["c"]
        cur = await db().execute("SELECT COUNT(*) c FROM jail_cases WHERE guild_id = ? AND status = 'active'", (gid,))
        active = (await cur.fetchone())["c"]
        cur = await db().execute("SELECT COUNT(*) c FROM jail_cases WHERE guild_id = ? AND status = 'pardoned'", (gid,))
        pardoned = (await cur.fetchone())["c"]
        cur = await db().execute("SELECT COUNT(DISTINCT user_id) c FROM jail_cases WHERE guild_id = ?", (gid,))
        unique_users = (await cur.fetchone())["c"]
        embed = build_embed(
            "Jail Statistics",
            None,
            fields=[
                ("Total Cases", str(total), True),
                ("Currently Active", str(active), True),
                ("Pardoned", str(pardoned), True),
                ("Unique Members Jailed", str(unique_users), True),
            ],
        )
        await interaction.followup.send(embed=embed)

    @jailstats.command(name="top", description="Most jailed users.")
    @trusted_only()
    async def top(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT user_id, COUNT(*) c FROM jail_cases WHERE guild_id = ? GROUP BY user_id ORDER BY c DESC LIMIT 10",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("Most Jailed", "No data yet."))
        lines = [f"{i+1}. <@{r['user_id']}> — {r['c']} case(s)" for i, r in enumerate(rows)]
        await interaction.followup.send(embed=build_embed("Most Jailed", "\n".join(lines)))

    @jailstats.command(name="moderators", description="Moderator statistics.")
    @trusted_only()
    async def moderators(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT moderator_id, COUNT(*) c FROM jail_cases WHERE guild_id = ? GROUP BY moderator_id ORDER BY c DESC LIMIT 10",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("Moderator Activity", "No data yet."))
        lines = [f"{i+1}. <@{r['moderator_id']}> — {r['c']} action(s)" for i, r in enumerate(rows)]
        await interaction.followup.send(embed=build_embed("Moderator Activity", "\n".join(lines)))

    @jailstats.command(name="activity", description="Recent jail actions.")
    @trusted_only()
    async def activity(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM action_logs WHERE guild_id = ? ORDER BY created_at DESC LIMIT 10",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("Recent Activity", "No recent actions."))
        lines = [f"<t:{r['created_at']}:R> — {r['action']} — <@{r['user_id']}>" for r in rows]
        await interaction.followup.send(embed=build_embed("Recent Activity", "\n".join(lines)))

    @jailstats.command(name="longest", description="Longest active sentences.")
    @trusted_only()
    async def longest(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND status = 'active' AND duration_seconds IS NOT NULL"
            " ORDER BY duration_seconds DESC LIMIT 10",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        cur2 = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND status = 'active' AND duration_seconds IS NULL",
            (interaction.guild.id,),
        )
        permanent = await cur2.fetchall()
        lines = [f"<@{r['user_id']}> — {format_duration(r['duration_seconds'])}" for r in rows]
        lines += [f"<@{r['user_id']}> — Permanent" for r in permanent]
        if not lines:
            return await interaction.followup.send(embed=build_embed("Longest Sentences", "No active sentences."))
        await interaction.followup.send(embed=build_embed("Longest Sentences", "\n".join(lines[:10])))

    @jailstats.command(name="oldest", description="Oldest jail records.")
    @trusted_only()
    async def oldest(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? ORDER BY created_at ASC LIMIT 10",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("Oldest Records", "No jail records yet."))
        lines = [f"#{r['case_id']} — <@{r['user_id']}> — <t:{r['created_at']}:D>" for r in rows]
        await interaction.followup.send(embed=build_embed("Oldest Records", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Statistics(bot))
