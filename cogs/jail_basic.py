import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_guild_config
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import trusted_only, is_exempt
from utils.jail_actions import jail_member, release_member
from utils.duration import parse_duration


class JailHistorySelect(discord.ui.UserSelect):
    """Member picker shown after choosing 'History' from /jailinfo."""

    def __init__(self):
        super().__init__(placeholder="Choose a member to view their jail history", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 15",
            (interaction.guild.id, member.id),
        )
        rows = await cur.fetchall()
        if not rows:
            embed = build_embed("Jail History", f"`{member}` has no jail history.")
        else:
            lines = [f"`{member}` — Case #{r['case_id']} — {r['status']} — {r['reason'] or 'No reason'}" for r in rows]
            embed = build_embed(f"Jail History — {member.display_name}", "\n".join(lines))
        await interaction.followup.send(embed=embed)


class JailHistoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(JailHistorySelect())


class JailInfoSelect(discord.ui.Select):
    """Top-level dropdown for /jailinfo: List or History."""

    def __init__(self):
        options = [
            discord.SelectOption(label="List", value="list", description="Everyone currently jailed."),
            discord.SelectOption(label="History", value="history", description="A member's full jail history."),
        ]
        super().__init__(placeholder="Choose what to view", options=options, custom_id="jailinfo_select")

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "list":
            await interaction.response.defer()
            cur = await db().execute(
                "SELECT * FROM jail_cases WHERE guild_id = ? AND status = 'active' ORDER BY created_at DESC",
                (interaction.guild.id,),
            )
            rows = await cur.fetchall()
            if not rows:
                embed = build_embed("Active Jail List", "No one is currently jailed.")
            else:
                lines = []
                for r in rows:
                    member = interaction.guild.get_member(r["user_id"])
                    name = f"`{member}`" if member else f"`{r['user_id']}`"
                    remaining = None
                    if r["duration_seconds"] is not None:
                        elapsed = now() - r["created_at"]
                        remaining = max(0, r["duration_seconds"] - elapsed)
                    lines.append(
                        f"{name} — Case #{r['case_id']} — {format_duration(remaining if r['duration_seconds'] is not None else None)} remaining"
                        f" — Reason: {r['reason'] or 'None'} — Evidence: {r['evidence'] or 'None'}"
                    )
                embed = build_embed("Active Jail List", "\n".join(lines[:25]))
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(
                embed=build_embed("Jail History", "Select a member below to view their jail history."),
                view=JailHistoryView(),
                ephemeral=True,
            )


class JailInfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(JailInfoSelect())


class JailBasic(commands.Cog):
    """
    Core jailing actions.

    Note on command naming: Discord does not allow a single word (like
    "jail") to be both a standalone command AND a group containing
    subcommands (e.g. "jail list"). Since /jail needs to work as a direct
    action ("/jail @user disruptive behavior"), the browsing UI lives
    under the standalone /jailinfo command instead (a dropdown, not a
    subcommand group), and moderator utilities that need a "/jail ..."
    style path (transfer, notify, history) live under /jailmod.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /jail - place a member in jail
    # ------------------------------------------------------------------
    @app_commands.command(name="jail", description="Jail a member.")
    @app_commands.describe(member="The member to jail", reason="Why they are being jailed",
                           duration="How long to jail for, e.g. 30s, 10m, 2hr, 1d, or permanent "
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
            duration_seconds = cfg["default_seconds"]
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
    @app_commands.describe(member="The jailed member to release", reason="Why they are being released")
    @trusted_only()
    async def release(self, interaction: discord.Interaction, member: discord.Member,
                       reason: str = "No reason provided"):
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
            interaction.guild, member, interaction.user, row["case_id"], "released", self.bot, reason=reason
        )
        await interaction.followup.send(embed=build_embed("Release", message) if success else error_embed(message))

    # ------------------------------------------------------------------
    # /jailinfo - dropdown: List / History
    # ------------------------------------------------------------------
    @app_commands.command(name="jailinfo", description="Browse jail records.")
    @trusted_only()
    async def jailinfo(self, interaction: discord.Interaction):
        embed = build_embed("Jail Info", "Choose what you'd like to view below.")
        await interaction.response.send_message(embed=embed, view=JailInfoView())


async def setup(bot: commands.Bot):
    await bot.add_cog(JailBasic(bot))
