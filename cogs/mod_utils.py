import datetime

import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_guild_config
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import trusted_only
from utils.duration import parse_duration


class ModUtils(commands.Cog):
    """
    Extra moderator tools for members already in jail. Grouped under
    /jailmod (not /jail) for the same naming-conflict reason as /sentence.
    Voice-related commands (disconnect, move to Jail VC) have been removed
    per spec — there is no jail voice channel in this build.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    jailmod = app_commands.Group(name="jailmod", description="Moderator tools for jailed members.")

    @jailmod.command(name="mute", description="Mute inside jail (server timeout).")
    @app_commands.describe(member="The jailed member", duration="Timeout length, e.g. 30s, 10m, 2h, 1d")
    @trusted_only()
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: str):
        await interaction.response.defer()
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.followup.send(embed=error_embed(str(exc)))
        try:
            await member.timeout(discord.utils.utcnow() + datetime.timedelta(seconds=seconds),
                                  reason=f"Muted in jail by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to time out that member."))
        await interaction.followup.send(embed=build_embed("Muted", f"{member.mention} has been muted for {format_duration(seconds)}."))

    @jailmod.command(name="transfer", description="Transfer a jailed member to a different cell channel.")
    @app_commands.describe(member="The jailed member", channel="The cell channel to transfer them to")
    @trusted_only()
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, channel: discord.TextChannel):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))

        old_channel = interaction.guild.get_channel(row["cell_channel_id"]) if row["cell_channel_id"] else None

        try:
            await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True,
                                           reason=f"Transferred by {interaction.user}")
            if old_channel is not None:
                await old_channel.set_permissions(member, overwrite=None, reason=f"Transferred by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to modify that channel."))

        await db().execute(
            "UPDATE jail_cases SET cell_channel_id = ?, notes = COALESCE(notes || char(10), '') || ? "
            "WHERE guild_id = ? AND case_id = ? AND status = 'active'",
            (channel.id, f"Transferred to {channel.name} by {interaction.user}", interaction.guild.id, row["case_id"]),
        )
        await db().commit()
        await interaction.followup.send(embed=build_embed(
            "Case Transferred", f"Case #{row['case_id']} ({member.mention}) has been transferred to {channel.mention}."))

    @jailmod.command(name="notify", description="Resend jail notification.")
    @app_commands.describe(member="The jailed member")
    @trusted_only()
    async def notify(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        try:
            await member.send(embed=build_embed(
                "Jail Notification",
                f"Reminder: you are jailed in {interaction.guild.name}. Case #{row['case_id']}. Reason: {row['reason']}"
            ))
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("Could not DM that member; their DMs may be closed."))
        await interaction.followup.send(embed=build_embed("Notification Sent", f"Resent jail notification to {member.mention}."))


async def setup(bot: commands.Bot):
    await bot.add_cog(ModUtils(bot))
