import discord
from discord import app_commands
from discord.ext import commands

from database import db, now
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import trusted_only
from utils.jail_actions import release_member
from utils.duration import parse_duration
from utils.notify import notify_and_log


class Extras(commands.Cog):
    """
    Situational jail commands modeled on real-world corrections concepts.

    /solitary, /probation, and /cellmate have been removed per spec.
    /visitation remains as the only command in this cog.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="visitation", description="Temporarily grant a non-jailed member access to a jail cell.")
    @app_commands.describe(member="The non-jailed member who may visit",
                            channel="The jail cell channel to grant access to",
                            duration="How long the visitation access lasts, e.g. 30s, 15m, 2hr, 1d")
    @trusted_only()
    async def visitation(self, interaction: discord.Interaction, member: discord.Member,
                          channel: discord.TextChannel, duration: str = "15m"):
        await interaction.response.defer()
        try:
            duration_seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.followup.send(embed=error_embed(str(exc)))

        try:
            await channel.set_permissions(member, view_channel=True, send_messages=True,
                                           reason=f"Visitation granted by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to modify that channel."))

        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND cell_channel_id = ? AND status = 'active'",
            (interaction.guild.id, channel.id),
        )
        occupant_case = await cur.fetchone()
        if occupant_case is not None:
            occupant = interaction.guild.get_member(occupant_case["user_id"])
            await notify_and_log(
                interaction.guild,
                action="visitation",
                user_id=occupant_case["user_id"],
                moderator_id=interaction.user.id,
                case_id=occupant_case["case_id"],
                detail=f"{member} granted visitation access for {format_duration(duration_seconds)}",
                dm_target=occupant,
                dm_title="You Have Received a Visit",
                dm_fields=[
                    ("Visitor", member.mention, True),
                    ("Cell", channel.mention, True),
                    ("Access Duration", format_duration(duration_seconds), True),
                    ("Case ID", f"#{occupant_case['case_id']}", True),
                ],
                log_title="Visitation Granted",
                log_fields=[
                    ("Occupant", f"<@{occupant_case['user_id']}>", True),
                    ("Visitor", member.mention, True),
                    ("Moderator", interaction.user.mention, True),
                    ("Cell", channel.mention, True),
                    ("Access Duration", format_duration(duration_seconds), True),
                    ("Case ID", f"#{occupant_case['case_id']}", True),
                ],
            )

        await interaction.followup.send(embed=build_embed(
            "Visitation Granted",
            f"{member.mention} may now access {channel.mention} for {format_duration(duration_seconds)}. "
            "Remove access manually afterward, or reduce with /cell lock if needed. Note: that cell "
            "is deleted automatically when the occupant is released, which also clears this access."
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Extras(bot))
