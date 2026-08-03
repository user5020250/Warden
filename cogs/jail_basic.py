import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_guild_config
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import trusted_only, is_exempt
from utils.jail_actions import jail_member, release_member
from utils.duration import parse_duration


class JailBasic(commands.Cog):
    """
    Core jailing actions.

    Note on command naming: Discord does not allow a single word (like
    "jail") to be both a standalone command AND a group containing
    subcommands (e.g. "jail list"). Since /jail needs to work as a direct
    action ("/jail @user disruptive behavior"), the browsing commands that
    were listed as "/jail list", "/jail info", "/jail history", and
    "/jail search" live under the /jailinfo group instead.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /jail - place a member in jail
    # ------------------------------------------------------------------
    @app_commands.command(name="jail", description="Jail a member.")
    @app_commands.describe(member="The member to jail", reason="Why they are being jailed",
                           duration="How long to jail for, e.g. 30s, 10m, 2h, 1d, or permanent "
                                     "(omit for the server default)")
    @trusted_only()
    async def jail(self, interaction: discord.Interaction, member: discord.Member,
                    reason: str = "No reason provided", duration: str | None = None):
        await interaction.response.defer()

        if member.id == interaction.user.id:
            return await interaction.followup.send(embed=error_embed("You cannot jail yourself."))
        if member.bot:
            return await interaction.followup.send(embed=error_embed("You cannot jail a bot."))
        if await is_exempt(member):
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is exempt from being jailed."))
        if member.top_role >= interaction.user.top_role and interaction.guild.owner_id != interaction.user.id:
            return await interaction.followup.send(embed=error_embed("You cannot jail someone with an equal or higher role."))

        cfg = await get_guild_config(interaction.guild.id)
        if duration is None:
            duration_seconds = cfg["default_minutes"] * 60
        else:
            try:
                duration_seconds = parse_duration(duration, allow_permanent=True)
            except ValueError as exc:
                return await interaction.followup.send(embed=error_embed(str(exc)))

        success, message, case_id = await jail_member(
            interaction.guild, member, interaction.user, reason, duration_seconds, self.bot
        )
        embed = build_embed("Jail", message) if success else error_embed(message)
        await interaction.followup.send(embed=embed)

    # ------------------------------------------------------------------
    # /release
    # ------------------------------------------------------------------
    @app_commands.command(name="release", description="Release a member.")
    @app_commands.describe(member="The jailed member to release")
    @trusted_only()
    async def release(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT case_id FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active'"
            " ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        success, message = await release_member(
            interaction.guild, member, interaction.user, row["case_id"], "released", self.bot
        )
        await interaction.followup.send(embed=build_embed("Release", message) if success else error_embed(message))

    # ------------------------------------------------------------------
    # /selfrelease - owner only / debug
    # ------------------------------------------------------------------
    @app_commands.command(name="selfrelease", description="Release yourself (Owner only or debug).")
    async def selfrelease(self, interaction: discord.Interaction):
        if interaction.user.id != interaction.guild.owner_id and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=error_embed("Only the server owner or an administrator can use this."), ephemeral=True
            )
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT case_id FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active'"
            " ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, interaction.user.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=error_embed("You are not currently jailed."))
        success, message = await release_member(
            interaction.guild, interaction.user, interaction.user, row["case_id"], "released", self.bot
        )
        await interaction.followup.send(embed=build_embed("Self Release", message) if success else error_embed(message))

    # ------------------------------------------------------------------
    # /jailinfo group -> list / info / history / search
    # ------------------------------------------------------------------
    jailinfo = app_commands.Group(name="jailinfo", description="Browse jail records.")

    @jailinfo.command(name="list", description="List all jailed users.")
    @trusted_only()
    async def jailinfo_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND status = 'active' ORDER BY created_at DESC",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("Active Jail List", "No one is currently jailed."))
        lines = []
        for r in rows:
            remaining = None
            if r["duration_seconds"] is not None:
                elapsed = now() - r["created_at"]
                remaining = max(0, r["duration_seconds"] - elapsed)
            lines.append(f"Case #{r['case_id']} — <@{r['user_id']}> — {format_duration(remaining if r['duration_seconds'] is not None else None)} remaining")
        await interaction.followup.send(embed=build_embed("Active Jail List", "\n".join(lines[:25])))

    @jailinfo.command(name="info", description="View jail information for a member.")
    @app_commands.describe(member="The member to look up")
    @trusted_only()
    async def jailinfo_info(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active'"
            " ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=build_embed("Jail Info", f"{member.mention} is not currently jailed."))
        elapsed = now() - row["created_at"]
        remaining = None if row["duration_seconds"] is None else max(0, row["duration_seconds"] - elapsed)
        embed = build_embed(
            f"Jail Info — {member.display_name}",
            None,
            fields=[
                ("Case ID", f"#{row['case_id']}", True),
                ("Moderator", f"<@{row['moderator_id']}>", True),
                ("Reason", row["reason"] or "None", False),
                ("Time Remaining", format_duration(remaining), True),
                ("Frozen", "Yes" if row["frozen"] else "No", True),
                ("On Probation", "Yes" if row["on_probation"] else "No", True),
            ],
        )
        await interaction.followup.send(embed=embed)

    @jailinfo.command(name="history", description="View punishment history for a member.")
    @app_commands.describe(member="The member to look up")
    @trusted_only()
    async def jailinfo_history(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 15",
            (interaction.guild.id, member.id),
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("History", f"{member.mention} has no jail history."))
        lines = [f"#{r['case_id']} — {r['status']} — {r['reason'] or 'No reason'}" for r in rows]
        await interaction.followup.send(embed=build_embed(f"History — {member.display_name}", "\n".join(lines)))

    @jailinfo.command(name="search", description="Search jail cases by user or case ID.")
    @app_commands.describe(member="Filter by member (optional)", case_id="Filter by case ID (optional)")
    @trusted_only()
    async def jailinfo_search(self, interaction: discord.Interaction,
                               member: discord.Member | None = None, case_id: int | None = None):
        await interaction.response.defer()
        if case_id is not None:
            cur = await db().execute(
                "SELECT * FROM jail_cases WHERE guild_id = ? AND case_id = ? ORDER BY created_at DESC LIMIT 15",
                (interaction.guild.id, case_id))
        elif member is not None:
            cur = await db().execute(
                "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 15",
                (interaction.guild.id, member.id))
        else:
            return await interaction.followup.send(embed=error_embed("Provide a member or a case ID to search."))
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("Search Results", "No matching cases found."))
        lines = [f"#{r['case_id']} — <@{r['user_id']}> — {r['status']} — {r['reason'] or 'No reason'}" for r in rows]
        await interaction.followup.send(embed=build_embed("Search Results", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(JailBasic(bot))
