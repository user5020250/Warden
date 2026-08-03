import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_guild_config
from utils.embeds import build_embed, error_embed
from utils.permissions import trusted_only


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

    @jailmod.command(name="warn", description="Warn a jailed user.")
    @app_commands.describe(member="The jailed member", reason="Reason for the warning")
    @trusted_only()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.defer()
        await db().execute(
            "INSERT INTO jail_warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (interaction.guild.id, member.id, interaction.user.id, reason, now()),
        )
        await db().commit()
        try:
            await member.send(embed=build_embed("Warning", f"You have been warned in {interaction.guild.name}: {reason}"))
        except discord.Forbidden:
            pass
        await interaction.followup.send(embed=build_embed("Warning Issued", f"{member.mention} has been warned: {reason}"))

    @jailmod.command(name="mute", description="Mute inside jail (server timeout).")
    @app_commands.describe(member="The jailed member", minutes="Timeout length in minutes")
    @trusted_only()
    async def mute(self, interaction: discord.Interaction, member: discord.Member, minutes: int):
        await interaction.response.defer()
        try:
            await member.timeout(discord.utils.utcnow() + __import__("datetime").timedelta(minutes=minutes),
                                  reason=f"Muted in jail by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to time out that member."))
        await interaction.followup.send(embed=build_embed("Muted", f"{member.mention} has been muted for {minutes} minute(s)."))

    @jailmod.command(name="nickname", description="Change nickname while jailed.")
    @app_commands.describe(member="The jailed member", nickname="New nickname")
    @trusted_only()
    async def nickname(self, interaction: discord.Interaction, member: discord.Member, nickname: str):
        await interaction.response.defer()
        try:
            await member.edit(nick=nickname, reason=f"Nickname changed while jailed by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to change that member's nickname."))
        await interaction.followup.send(embed=build_embed("Nickname Updated", f"{member.mention}'s nickname was changed to {nickname}."))

    @jailmod.command(name="transfer", description="Transfer to another jail category.")
    @app_commands.describe(member="The jailed member", category="The category to move their case reference to")
    @trusted_only()
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, category: discord.CategoryChannel):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT case_id FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        await db().execute(
            "UPDATE jail_cases SET notes = COALESCE(notes || char(10), '') || ? WHERE case_id = ?",
            (f"Transferred to category '{category.name}' by {interaction.user}", row["case_id"]),
        )
        await db().commit()
        await interaction.followup.send(embed=build_embed(
            "Case Transferred", f"Case #{row['case_id']} has been noted as transferred to {category.name}."))

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

    @jailmod.command(name="restore", description="Restore roles manually.")
    @app_commands.describe(member="The member to restore roles for")
    @trusted_only()
    async def restore(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        row = await cur.fetchone()
        if row is None or not row["role_backup"]:
            return await interaction.followup.send(embed=error_embed("No role backup found for that member."))
        ids = [int(x) for x in row["role_backup"].split(",") if x]
        roles = [interaction.guild.get_role(i) for i in ids]
        roles = [r for r in roles if r is not None]
        if not roles:
            return await interaction.followup.send(embed=error_embed("None of the backed-up roles still exist."))
        try:
            await member.add_roles(*roles, reason=f"Manual role restoration by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to modify that member's roles."))
        await interaction.followup.send(embed=build_embed("Roles Restored", f"Restored {len(roles)} role(s) to {member.mention}."))


async def setup(bot: commands.Bot):
    await bot.add_cog(ModUtils(bot))
