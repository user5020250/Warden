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

        await interaction.followup.send(embed=build_embed(
            "Visitation Granted",
            f"{member.mention} may now access {channel.mention} for {format_duration(duration_seconds)}. "
            "Remove access manually afterward, or reduce with /cell lock if needed. Note: that cell "
            "is deleted automatically when the occupant is released, which also clears this access."
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Extras(bot))
