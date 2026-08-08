import discord
from discord import app_commands
from discord.ext import commands

from database import db, get_guild_config
from utils.embeds import build_embed, error_embed
from utils.permissions import trusted_only
from utils.notify import notify_and_log


async def _get_cell_channel(guild: discord.Guild, member: discord.Member):
    """Looks up the private cell channel tied to a member's active jail case."""
    cur = await db().execute(
        "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active'"
        " ORDER BY created_at DESC LIMIT 1",
        (guild.id, member.id),
    )
    case = await cur.fetchone()
    if case is None:
        return None, "not_jailed", None
    if not case["cell_channel_id"]:
        return None, "no_cell", None
    channel = guild.get_channel(case["cell_channel_id"])
    if channel is None:
        return None, "no_cell", None
    return channel, None, case["case_id"]


class Cell(commands.Cog):
    """
    Jail cell channel controls. Each jailed member has their own private
    cell channel (created by /jail, deleted automatically on release), so
    these commands take the member whose cell you want to act on.
    /cell clean, /cell purge, and /cell announce have been removed per
    spec, and no jail voice-channel commands are included.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    cell = app_commands.Group(name="cell", description="Manage a jailed member's cell channel.")

    @cell.command(name="lock", description="Lock a member's jail cell.")
    @app_commands.describe(member="The jailed member whose cell should be locked")
    @trusted_only()
    async def lock(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        channel, err, case_id = await _get_cell_channel(interaction.guild, member)
        if err == "not_jailed":
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if err == "no_cell" or channel is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} doesn't have a cell channel."))
        overwrite = channel.overwrites_for(member)
        overwrite.send_messages = False
        await channel.set_permissions(member, overwrite=overwrite, reason=f"Cell locked by {interaction.user}")

        await notify_and_log(
            interaction.guild,
            action="cell_lock",
            user_id=member.id,
            moderator_id=interaction.user.id,
            case_id=case_id,
            detail=f"Cell {channel.name} locked",
            dm_target=member,
            dm_title="Your Cell Has Been Locked",
            dm_description="You can no longer send messages in your cell channel until it is unlocked.",
            dm_fields=[("Cell", channel.mention, True), ("Case ID", f"#{case_id}", True)],
            log_title="Cell Locked",
            log_fields=[
                ("Member", f"{member.mention} ({member.id})", True),
                ("Moderator", interaction.user.mention, True),
                ("Cell", channel.mention, True),
                ("Case ID", f"#{case_id}", True),
            ],
        )
        await interaction.followup.send(embed=build_embed(
            "Cell Locked", f"{member.mention} can no longer send messages in {channel.mention}."))

    @cell.command(name="unlock", description="Unlock a member's jail cell.")
    @app_commands.describe(member="The jailed member whose cell should be unlocked")
    @trusted_only()
    async def unlock(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        channel, err, case_id = await _get_cell_channel(interaction.guild, member)
        if err == "not_jailed":
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if err == "no_cell" or channel is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} doesn't have a cell channel."))
        overwrite = channel.overwrites_for(member)
        overwrite.send_messages = True
        await channel.set_permissions(member, overwrite=overwrite, reason=f"Cell unlocked by {interaction.user}")

        await notify_and_log(
            interaction.guild,
            action="cell_unlock",
            user_id=member.id,
            moderator_id=interaction.user.id,
            case_id=case_id,
            detail=f"Cell {channel.name} unlocked",
            dm_target=member,
            dm_title="Your Cell Has Been Unlocked",
            dm_description="You may send messages in your cell channel again.",
            dm_fields=[("Cell", channel.mention, True), ("Case ID", f"#{case_id}", True)],
            log_title="Cell Unlocked",
            log_fields=[
                ("Member", f"{member.mention} ({member.id})", True),
                ("Moderator", interaction.user.mention, True),
                ("Cell", channel.mention, True),
                ("Case ID", f"#{case_id}", True),
            ],
        )
        await interaction.followup.send(embed=build_embed(
            "Cell Unlocked", f"{member.mention} can send messages in {channel.mention} again."))

    @cell.command(name="slowmode", description="Set slowmode in a member's jail cell.")
    @app_commands.describe(member="The jailed member whose cell should be updated",
                            seconds="Slowmode delay in seconds (0 to disable)")
    @trusted_only()
    async def slowmode(self, interaction: discord.Interaction, member: discord.Member, seconds: app_commands.Range[int, 0, 21600]):
        await interaction.response.defer()
        channel, err, case_id = await _get_cell_channel(interaction.guild, member)
        if err == "not_jailed":
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if err == "no_cell" or channel is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} doesn't have a cell channel."))
        await channel.edit(slowmode_delay=seconds)

        await notify_and_log(
            interaction.guild,
            action="cell_slowmode",
            user_id=member.id,
            moderator_id=interaction.user.id,
            case_id=case_id,
            detail=f"Cell {channel.name} slowmode set to {seconds}s",
            dm_target=member,
            dm_title="Your Cell's Slowmode Has Changed",
            dm_fields=[
                ("Cell", channel.mention, True),
                ("Slowmode", f"{seconds} second(s)", True),
                ("Case ID", f"#{case_id}", True),
            ],
            log_title="Cell Slowmode Updated",
            log_fields=[
                ("Member", f"{member.mention} ({member.id})", True),
                ("Moderator", interaction.user.mention, True),
                ("Cell", channel.mention, True),
                ("Slowmode", f"{seconds} second(s)", True),
                ("Case ID", f"#{case_id}", True),
            ],
        )
        await interaction.followup.send(embed=build_embed(
            "Slowmode Updated", f"Slowmode in {channel.mention} set to {seconds} second(s)."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Cell(bot))
