import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_active_case, log_action
from utils.embeds import build_embed, error_embed
from utils.permissions import staff_only


class Cellmate(commands.Cog):
    """
    Lets a second member be granted standing access to someone's jail cell
    channel (as opposed to /cell visit, which is a temporary, expiring
    grant). A cellmate keeps access until explicitly removed or the case
    they're attached to closes.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    cellmate = app_commands.Group(name="cellmate", description="Share a jail cell with another member.")

    @cellmate.command(name="list", description="Shows the members sharing a jail cell.")
    @app_commands.describe(member="The jailed member whose cell you want to check")
    @staff_only()
    async def list_cellmates(self, interaction: discord.Interaction, member: discord.Member):
        case = await get_active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.response.send_message(embed=error_embed(f"{member.mention} is not currently jailed."))
        cur = await db().execute(
            "SELECT * FROM cellmates WHERE guild_id = ? AND case_id = ?", (interaction.guild.id, case["case_id"])
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.response.send_message(embed=build_embed("Cellmates", f"{member.mention} has no cellmates."))
        lines = "\n".join(f"<@{r['member_id']}>" for r in rows)
        await interaction.response.send_message(embed=build_embed(f"Cellmates — {member}", lines))

    @cellmate.command(name="add", description="Adds a member to a shared jail cell.")
    @app_commands.describe(member="The jailed member whose cell to share", cellmate="The member to add as a cellmate")
    @staff_only()
    async def add(self, interaction: discord.Interaction, member: discord.Member, cellmate: discord.Member):
        await interaction.response.defer()
        case = await get_active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if not case["cell_channel_id"]:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} does not have a cell channel."))
        cell_channel = interaction.guild.get_channel(case["cell_channel_id"])
        if cell_channel is None:
            return await interaction.followup.send(embed=error_embed("That cell channel no longer exists."))

        cur = await db().execute(
            "SELECT 1 FROM cellmates WHERE guild_id = ? AND case_id = ? AND member_id = ?",
            (interaction.guild.id, case["case_id"], cellmate.id),
        )
        if await cur.fetchone():
            return await interaction.followup.send(embed=error_embed(f"{cellmate.mention} is already a cellmate on case `#{case['case_id']}`."))

        try:
            await cell_channel.set_permissions(cellmate, view_channel=True, send_messages=True, read_message_history=True,
                                                reason=f"Added as cellmate by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to modify that channel."))

        await db().execute(
            "INSERT INTO cellmates (guild_id, case_id, member_id, added_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (interaction.guild.id, case["case_id"], cellmate.id, interaction.user.id, now()),
        )
        await db().commit()
        await log_action(interaction.guild.id, "cellmate_added", user_id=cellmate.id, moderator_id=interaction.user.id,
                          case_id=case["case_id"], detail=f"Added as cellmate to {member}")

        await interaction.followup.send(embed=build_embed(
            "Cellmate Added", f"{cellmate.mention} now shares {cell_channel.mention} with {member.mention}."
        ))

    @cellmate.command(name="remove", description="Removes a member from a shared jail cell.")
    @app_commands.describe(member="The cellmate to remove")
    @staff_only()
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM cellmates WHERE guild_id = ? AND member_id = ?", (interaction.guild.id, member.id)
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not a cellmate on any active case."))

        for row in rows:
            cur2 = await db().execute(
                "SELECT cell_channel_id FROM jail_cases WHERE guild_id = ? AND case_id = ? AND status = 'active'",
                (interaction.guild.id, row["case_id"]),
            )
            case_row = await cur2.fetchone()
            if case_row and case_row["cell_channel_id"]:
                channel = interaction.guild.get_channel(case_row["cell_channel_id"])
                if channel is not None:
                    try:
                        await channel.set_permissions(member, overwrite=None, reason=f"Removed as cellmate by {interaction.user}")
                    except discord.Forbidden:
                        pass

        await db().execute("DELETE FROM cellmates WHERE guild_id = ? AND member_id = ?", (interaction.guild.id, member.id))
        await db().commit()
        await log_action(interaction.guild.id, "cellmate_removed", user_id=member.id, moderator_id=interaction.user.id)

        await interaction.followup.send(embed=build_embed("Cellmate Removed", f"{member.mention} has been removed from their shared cell(s)."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Cellmate(bot))
