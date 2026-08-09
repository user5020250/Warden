import discord
from discord import app_commands
from discord.ext import commands

from database import set_guild_config, get_guild_config
from utils.embeds import build_embed, error_embed


class Setup(commands.Cog):
    """One-time server setup for the jail system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="jailsetup", description="Sets up the jail role, category, and log channel.")
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
                name="Jailed", color=discord.Color.default(), reason="Warden setup"
            )

        # Category that will hold the jail cell channels
        category = guild.get_channel(cfg["jail_category_id"]) if cfg["jail_category_id"] else None
        if category is None:
            category = discord.utils.get(guild.categories, name="Jail")
        if category is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                jail_role: discord.PermissionOverwrite(view_channel=False),
            }
            category = await guild.create_category("Jail", overwrites=overwrites, reason="Warden setup")
        else:
            # Deny the jail role at the category level even on a re-run / pre-existing
            # category, so jailed members only ever see their own cell channel.
            await category.set_permissions(guild.default_role, view_channel=False, reason="Warden setup")
            await category.set_permissions(jail_role, view_channel=False, reason="Warden setup")

        # Deny jailed members from seeing every other channel in the server
        for channel in guild.channels:
            if channel.category_id == category.id:
                continue
            try:
                overwrite = channel.overwrites_for(jail_role)
                overwrite.view_channel = False
                await channel.set_permissions(jail_role, overwrite=overwrite, reason="Warden setup")
            except discord.Forbidden:
                continue

        # Single moderation log channel: jail actions, warnings, reports,
        # and appeal decisions all post here.
        log_channel_id = cfg["log_channel_id"]
        if not log_channel_id:
            log_channel = discord.utils.get(guild.text_channels, name="jail-logs")
            if log_channel is None:
                log_channel = await guild.create_text_channel(
                    "jail-logs",
                    overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                    reason="Warden setup",
                )
            log_channel_id = log_channel.id

        await set_guild_config(
            guild.id,
            jail_role_id=jail_role.id,
            jail_category_id=category.id,
            log_channel_id=log_channel_id,
        )

        embed = build_embed(
            "Warden Setup Complete",
            "The jail role, jail category, and log channel have been created and linked. Individual "
            "cell channels are created automatically by `/jail` and removed on release.",
            fields=[
                ("Jail Role", jail_role.mention, True),
                ("Jail Category", f"`{category.name}`", True),
                ("Log Channel", f"<#{log_channel_id}>", True),
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
