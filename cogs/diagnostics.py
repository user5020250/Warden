import discord
from discord import app_commands
from discord.ext import commands

from database import db, get_guild_config
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import staff_only
from utils.pagination import Paginator


class Diagnostics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="jailhistory", description="Shows a member's complete jail history.")
    @app_commands.describe(member="The member to look up")
    @staff_only()
    async def jailhistory(self, interaction: discord.Interaction, member: discord.Member):
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (interaction.guild.id, member.id),
        )
        rows = await cur.fetchall()
        lines = []
        for r in rows:
            duration_text = format_duration(r["duration_seconds"])
            lines.append(
                f"`#{r['case_id']}` — Status: `{r['status']}` — Duration: `{duration_text}` — "
                f"<t:{r['created_at']}:d> — {r['reason'] or 'No reason provided'}"
            )
        view = Paginator(f"Jail History — {member}", lines, f"{member.mention} has no jail history.")
        await interaction.response.send_message(embed=view.render(), view=view)

    @app_commands.command(name="jailsearch", description="Searches jail cases by member, case ID, reason, moderator, or other information.")
    @app_commands.describe(query="A case ID, member, moderator, or a word to search reasons for")
    @staff_only()
    async def jailsearch(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        matches = {}

        if query.isdigit():
            cur = await db().execute(
                "SELECT * FROM jail_cases WHERE guild_id = ? AND case_id = ?", (interaction.guild.id, int(query))
            )
            for row in await cur.fetchall():
                matches[(row["case_id"], row["created_at"])] = row

        member = None
        cleaned = query.strip("<@!>")
        if cleaned.isdigit():
            member = interaction.guild.get_member(int(cleaned))
        if member is None:
            member = discord.utils.find(
                lambda m: m.name.lower() == query.lower() or (m.nick and m.nick.lower() == query.lower()),
                interaction.guild.members,
            )
        if member is not None:
            cur = await db().execute(
                "SELECT * FROM jail_cases WHERE guild_id = ? AND (user_id = ? OR moderator_id = ?)",
                (interaction.guild.id, member.id, member.id),
            )
            for row in await cur.fetchall():
                matches[(row["case_id"], row["created_at"])] = row

        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND reason LIKE ?", (interaction.guild.id, f"%{query}%")
        )
        for row in await cur.fetchall():
            matches[(row["case_id"], row["created_at"])] = row

        rows = sorted(matches.values(), key=lambda r: r["created_at"], reverse=True)
        lines = [
            f"`#{r['case_id']}` — <@{r['user_id']}> — Status: `{r['status']}` — {r['reason'] or 'No reason provided'}"
            for r in rows
        ]
        view = Paginator(f"Search Results — `{query}`", lines, "No matching cases were found.")
        await interaction.followup.send(embed=view.render(), view=view)

    @app_commands.command(name="jaillogs", description="Shows recent jail-system events.")
    @staff_only()
    async def jaillogs(self, interaction: discord.Interaction):
        cur = await db().execute(
            "SELECT * FROM action_logs WHERE guild_id = ? ORDER BY created_at DESC LIMIT 100",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        lines = []
        for r in rows:
            who = f" — <@{r['moderator_id']}>" if r["moderator_id"] else ""
            target = f" — <@{r['user_id']}>" if r["user_id"] else ""
            case_ref = f" — `#{r['case_id']}`" if r["case_id"] else ""
            lines.append(f"<t:{r['created_at']}:f> — `{r['action']}`{target}{who}{case_ref}")
        view = Paginator("Jail Logs", lines, "No jail-system events have been recorded yet.")
        await interaction.response.send_message(embed=view.render(), view=view)

    @app_commands.command(name="jaildiagnose", description="Checks Warden for configuration, database, role, channel, cell, and case problems.")
    @app_commands.checks.has_permissions(administrator=True)
    async def jaildiagnose(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        issues = []

        cfg = await get_guild_config(guild.id)
        jail_role = guild.get_role(cfg["jail_role_id"]) if cfg["jail_role_id"] else None
        category = guild.get_channel(cfg["jail_category_id"]) if cfg["jail_category_id"] else None
        log_channel = guild.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None

        if jail_role is None:
            issues.append("No valid jail role is configured. Run `/jailsetup` or `/jailconfig role`.")
        if category is None:
            issues.append("No valid jail category is configured. Run `/jailsetup` or `/jailconfig category`.")
        if log_channel is None:
            issues.append("No valid log channel is configured. Run `/jailsetup` or `/jailconfig logchannel`.")

        me = guild.me
        if not me.guild_permissions.manage_roles:
            issues.append("I am missing the Manage Roles permission.")
        if not me.guild_permissions.manage_channels:
            issues.append("I am missing the Manage Channels permission.")
        if jail_role is not None and jail_role >= me.top_role:
            issues.append("The jail role is positioned above or equal to my own top role, so I can't assign or remove it.")

        try:
            await db().execute("SELECT 1")
        except Exception:
            issues.append("The database connection is not responding.")

        cur = await db().execute("SELECT * FROM jail_cases WHERE guild_id = ? AND status = 'active'", (guild.id,))
        active_cases = await cur.fetchall()
        for case in active_cases:
            member = guild.get_member(case["user_id"])
            if member is None:
                issues.append(f"Case `#{case['case_id']}` is active but the member is no longer in the server.")
                continue
            if jail_role is not None and jail_role not in member.roles:
                issues.append(f"Case `#{case['case_id']}` is active but {member.mention} does not have the jail role.")
            if case["cell_channel_id"] and guild.get_channel(case["cell_channel_id"]) is None:
                issues.append(f"Case `#{case['case_id']}` references a cell channel that no longer exists.")

        if issues:
            embed = build_embed("Diagnostics — Issues Found", "\n".join(f"- {i}" for i in issues))
        else:
            embed = build_embed("Diagnostics — All Clear", "No configuration, database, role, channel, cell, or case problems were found.")
        await interaction.followup.send(embed=embed)

    @jaildiagnose.error
    async def jaildiagnose_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(embed=error_embed("You need Administrator permission to run this."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Diagnostics(bot))
