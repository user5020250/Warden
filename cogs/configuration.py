import discord
from discord import app_commands
from discord.ext import commands

from database import set_guild_config, get_guild_config, reset_guild_config
from utils.embeds import build_embed, error_embed, format_duration
from utils.duration import parse_duration


class Configuration(commands.Cog):
    """Server-level configuration for the jail system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    jailconfig = app_commands.Group(name="jailconfig", description="Configure Warden.",
                                     default_permissions=discord.Permissions(administrator=True))

    @jailconfig.command(name="view", description="Displays the current Warden configuration.")
    async def view(self, interaction: discord.Interaction):
        cfg = await get_guild_config(interaction.guild.id)
        jail_role = interaction.guild.get_role(cfg["jail_role_id"]) if cfg["jail_role_id"] else None
        category = interaction.guild.get_channel(cfg["jail_category_id"]) if cfg["jail_category_id"] else None
        log_channel = interaction.guild.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None

        embed = build_embed(
            "Warden Configuration",
            None,
            fields=[
                ("Jail Role", jail_role.mention if jail_role else "Not configured", True),
                ("Jail Category", f"`{category.name}`" if category else "Not configured", True),
                ("Log Channel", log_channel.mention if log_channel else "Not configured", True),
                ("Default Jail Duration", f"`{format_duration(cfg['default_seconds'])}`", True),
                ("AutoJail", "`Enabled`" if cfg["autojail_enabled"] else "`Disabled`", True),
            ],
        )
        await interaction.response.send_message(embed=embed)

    @jailconfig.command(name="role", description="Sets the jail role.")
    @app_commands.describe(role="The role used to mark jailed members")
    async def role(self, interaction: discord.Interaction, role: discord.Role):
        await set_guild_config(interaction.guild.id, jail_role_id=role.id)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Jail role set to {role.mention}."))

    @jailconfig.command(name="category", description="Sets the jail-cell category.")
    @app_commands.describe(category="The category that will hold jail cell channels")
    async def category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await set_guild_config(interaction.guild.id, jail_category_id=category.id)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Jail category set to `{category.name}`."))

    @jailconfig.command(name="logchannel", description="Sets the moderation log channel.")
    @app_commands.describe(channel="Channel where jail actions, warnings, reports, and appeals are logged")
    async def logchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await set_guild_config(interaction.guild.id, log_channel_id=channel.id)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Log channel set to {channel.mention}."))

    @jailconfig.command(name="defaulttime", description="Sets the default jail duration.")
    @app_commands.describe(duration="Default sentence length, e.g. 30s, 10m, 2hr, 1d, or permanent")
    async def defaulttime(self, interaction: discord.Interaction, duration: str):
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.response.send_message(embed=error_embed(str(exc)))
        await set_guild_config(interaction.guild.id, default_seconds=seconds)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Default jail duration set to `{format_duration(seconds)}`."))

    @jailconfig.command(name="reset", description="Resets Warden configuration to its defaults.")
    async def reset(self, interaction: discord.Interaction):
        await reset_guild_config(interaction.guild.id)
        await interaction.response.send_message(embed=build_embed(
            "Configuration Reset", "Warden configuration has been reset to its defaults. Run `/jailsetup` again to recreate the role, category, and log channel."
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Configuration(bot))
