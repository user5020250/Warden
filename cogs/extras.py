import discord
from discord import app_commands
from discord.ext import commands

from database import db, now
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import trusted_only
from utils.jail_actions import release_member
from utils.duration import parse_duration


class Extras(commands.Cog):
    """
    Situational jail commands modeled on real-world corrections concepts.

    Two commands from the original list were removed as duplicates of
    functionality that already exists elsewhere:
      - /parole was functionally identical to an early, conditional
        release, which /probation already covers (release with monitoring).
      - /goodbehavior was functionally identical to /sentence reduce
        (reducing time remaining), just with a fixed narrative reason.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="solitary", description="Place a jailed user in stricter isolation.")
    @app_commands.describe(member="The jailed member",
                            duration="Extra time added for the isolation period, e.g. 30s, 10m, 2h, 1d")
    @trusted_only()
    async def solitary(self, interaction: discord.Interaction, member: discord.Member, duration: str = "30m"):
        await interaction.response.defer()
        try:
            added_seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.followup.send(embed=error_embed(str(exc)))

        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        case = await cur.fetchone()
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))

        if case["cell_channel_id"]:
            cell_channel = interaction.guild.get_channel(case["cell_channel_id"])
            if cell_channel is not None:
                try:
                    overwrite = cell_channel.overwrites_for(member)
                    overwrite.send_messages = False
                    overwrite.add_reactions = False
                    await cell_channel.set_permissions(member, overwrite=overwrite,
                                                        reason=f"Solitary confinement by {interaction.user}")
                except discord.Forbidden:
                    pass

        new_duration = None
        if case["duration_seconds"] is not None:
            elapsed = now() - case["created_at"]
            remaining = max(0, case["duration_seconds"] - elapsed)
            new_duration = elapsed + remaining + added_seconds
            await db().execute("UPDATE jail_cases SET duration_seconds = ? WHERE case_id = ? AND guild_id = ?",
                                (new_duration, case["case_id"], interaction.guild.id))
            await db().commit()

        try:
            await member.send(embed=build_embed(
                "Solitary Confinement",
                f"You have been placed in stricter isolation in {interaction.guild.name}. "
                f"You can no longer send messages, even in the jail cell, and {format_duration(added_seconds)} "
                "were added to your sentence."
            ))
        except discord.Forbidden:
            pass

        await interaction.followup.send(embed=build_embed(
            "Solitary Confinement",
            f"{member.mention} has been placed in solitary confinement. {format_duration(added_seconds)} added to case #{case['case_id']}."
        ))

    @app_commands.command(name="probation", description="Release a jailed user early, with monitoring.")
    @app_commands.describe(member="The jailed member", reason="Conditions of the release")
    @trusted_only()
    async def probation(self, interaction: discord.Interaction, member: discord.Member,
                         reason: str = "Released early under monitoring."):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        case = await cur.fetchone()
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))

        await db().execute("UPDATE jail_cases SET on_probation = 1, notes = COALESCE(notes || char(10), '') || ? WHERE case_id = ?",
                            (f"Probation: {reason}", case["case_id"]))
        await db().commit()

        success, message = await release_member(interaction.guild, member, interaction.user,
                                                  case["case_id"], "released", self.bot)
        await interaction.followup.send(embed=build_embed(
            "Probation Granted",
            f"{member.mention} was released early under monitoring. {message}\nConditions: {reason}\n\n"
            "Note: if this member is jailed again while flagged for probation, moderators should treat it as a repeat "
            "offense (consider /sentence extend or /solitary)."
        ) if success else error_embed(message))

    @app_commands.command(name="visitation", description="Allow temporary access to visit a jailed user's cell.")
    @app_commands.describe(member="The jailed member whose cell is being visited",
                            visitor="The member who may temporarily visit the jail cell",
                            duration="How long the visitation access lasts, e.g. 30s, 15m, 2h, 1d")
    @trusted_only()
    async def visitation(self, interaction: discord.Interaction, member: discord.Member,
                          visitor: discord.Member, duration: str = "15m"):
        await interaction.response.defer()
        try:
            duration_seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.followup.send(embed=error_embed(str(exc)))

        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        case = await cur.fetchone()
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if not case["cell_channel_id"]:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} doesn't have a cell channel."))
        text_channel = interaction.guild.get_channel(case["cell_channel_id"])
        if text_channel is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention}'s cell channel no longer exists."))

        try:
            await text_channel.set_permissions(visitor, view_channel=True, send_messages=True,
                                                reason=f"Visitation granted by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to modify that channel."))

        await interaction.followup.send(embed=build_embed(
            "Visitation Granted",
            f"{visitor.mention} may now access {text_channel.mention} for {format_duration(duration_seconds)}. "
            "Remove access manually afterward, or reduce with /cell lock if needed. Note: that cell "
            "is deleted automatically when the occupant is released, which also clears this access."
        ))

    @app_commands.command(name="cellmate", description="Assign another jailed member's case to the same jail cell.")
    @app_commands.describe(member="An already jailed member", cellmate="Another member to jail into the same cell")
    @trusted_only()
    async def cellmate(self, interaction: discord.Interaction, member: discord.Member, cellmate: discord.Member):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        case = await cur.fetchone()
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))

        from utils.jail_actions import jail_member as do_jail
        success, msg, new_case_id = await do_jail(
            interaction.guild, cellmate, interaction.user,
            f"Assigned as cellmate to case #{case['case_id']} ({member.display_name})",
            case["duration_seconds"] if case["duration_seconds"] is None else max(
                0, case["duration_seconds"] - (now() - case["created_at"])), self.bot,
        )
        await interaction.followup.send(embed=build_embed("Cellmate Assigned", msg) if success else error_embed(msg))


async def setup(bot: commands.Bot):
    await bot.add_cog(Extras(bot))
