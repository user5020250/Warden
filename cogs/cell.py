import discord
from discord import app_commands
from discord.ext import commands

from database import now, get_active_case, add_visitation
from utils.embeds import build_embed, error_embed, format_duration
from utils.duration import parse_duration
from utils.permissions import staff_only


class Cell(commands.Cog):
    """
    Temporary jail-cell access, distinct from /cellmate: a visitation
    automatically expires and is revoked by the scheduler, rather than
    staying until someone removes it by hand.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    cell = app_commands.Group(name="cell", description="Jail cell channel controls.")

    @cell.command(name="visit", description="Grants a non-jailed member temporary access to a jail cell.")
    @app_commands.describe(member="The jailed member whose cell is being visited", visitor="The member being granted access",
                            duration="How long the visit lasts, e.g. 30s, 15m, 2hr, 1d")
    @staff_only()
    async def visit(self, interaction: discord.Interaction, member: discord.Member, visitor: discord.Member, duration: str):
        await interaction.response.defer()
        case = await get_active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if not case["cell_channel_id"]:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} does not have a cell channel."))
        cell_channel = interaction.guild.get_channel(case["cell_channel_id"])
        if cell_channel is None:
            return await interaction.followup.send(embed=error_embed("That cell channel no longer exists."))

        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.followup.send(embed=error_embed(str(exc)))
        if seconds is None:
            return await interaction.followup.send(embed=error_embed("A visitation cannot be permanent."))

        try:
            await cell_channel.set_permissions(visitor, view_channel=True, send_messages=True, read_message_history=True,
                                                reason=f"Visitation granted by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to modify that channel."))

        expires_at = now() + seconds
        await add_visitation(interaction.guild.id, cell_channel.id, visitor.id, member.id, case["case_id"], interaction.user.id, expires_at)

        await interaction.followup.send(embed=build_embed(
            "Visitation Granted",
            f"{visitor.mention} may now access {cell_channel.mention} for `{format_duration(seconds)}`.",
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Cell(bot))
