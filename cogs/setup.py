import discord
from discord import app_commands
from discord.ext import commands

from database import set_guild_config, get_guild_config
from utils.embeds import build_embed, error_embed
from utils.permissions import trusted_only


class Setup(commands.Cog):
    """One-time server setup for the jail system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="jailsetup", description="Sets up the jail role, category, log channel, and appeal channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def jailsetup(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        cfg = await get_guild_config(guild.id)

        # Reuse an existing jail role if one is already configured and valid
        jail_role = guild.get_role(cfg["jail_role_id"]) if cfg["jail_role_id"] else None
        if jail_role is None:
            jail_role = discord.utils.get(guild.roles, name="Jailed")
        if jail_role is None:
            jail_role = await guild.create_role(
                name="Jailed", color=discord.Color.default(), reason="Jail system setup"
            )

        # Category that will hold the jail channels
        category = guild.get_channel(cfg["jail_category_id"]) if cfg["jail_category_id"] else None
        if category is None:
            category = discord.utils.get(guild.categories, name="Jail")
        if category is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                jail_role: discord.PermissionOverwrite(view_channel=False),
            }
            category = await guild.create_category("Jail", overwrites=overwrites, reason="Jail system setup")
        else:
            # Deny the jail role at the category level even on a re-run / pre-existing
            # category, so jailed members only ever see their own cell channel, not
            # every other jailed member's cell.
            await category.set_permissions(guild.default_role, view_channel=False, reason="Jail system setup")
            await category.set_permissions(jail_role, view_channel=False, reason="Jail system setup")

        # This bot no longer uses a single shared jail-cell channel — each jailed
        # member gets their own private "cell-N" channel created by /jail and
        # removed automatically on release. Clean up a legacy shared channel if
        # one exists from an older setup.
        legacy_jail_channel = discord.utils.get(category.channels, name="jail-cell")
        if legacy_jail_channel is not None:
            try:
                await legacy_jail_channel.delete(reason="Jail system setup: shared jail-cell channel is no longer used")
            except discord.Forbidden:
                pass

        # Deny jailed members from seeing every other channel
        for channel in guild.channels:
            if channel.category_id == category.id:
                continue
            try:
                overwrite = channel.overwrites_for(jail_role)
                overwrite.view_channel = False
                await channel.set_permissions(jail_role, overwrite=overwrite, reason="Jail system setup")
            except discord.Forbidden:
                continue

        # Log + appeal channels default to staff-only text channels
        log_channel_id = cfg["log_channel_id"]
        if not log_channel_id:
            log_channel = discord.utils.get(guild.text_channels, name="jail-logs")
            if log_channel is None:
                log_channel = await guild.create_text_channel(
                    "jail-logs",
                    overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                    reason="Jail system setup",
                )
            log_channel_id = log_channel.id

        appeal_channel_id = cfg["appeal_channel_id"]
        if not appeal_channel_id:
            appeal_channel = discord.utils.get(guild.text_channels, name="jail-appeals")
            if appeal_channel is None:
                appeal_channel = await guild.create_text_channel(
                    "jail-appeals",
                    overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                    reason="Jail system setup",
                )
            appeal_channel_id = appeal_channel.id

        await set_guild_config(
            guild.id,
            jail_role_id=jail_role.id,
            jail_category_id=category.id,
            log_channel_id=log_channel_id,
            appeal_channel_id=appeal_channel_id,
        )

        embed = build_embed(
            "Jail System Ready",
            "The jail role, category, log channel, and appeal channel have been created and linked. "
            "Individual cell channels are created automatically by /jail and removed on release.",
            fields=[
                ("Jail Role", jail_role.mention, True),
                ("Jail Category", category.name, True),
                ("Log Channel", f"<#{log_channel_id}>", True),
                ("Appeal Channel", f"<#{appeal_channel_id}>", True),
            ],
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @jailsetup.error
    async def jailsetup_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=error_embed("You need Administrator permission to run this."), ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
