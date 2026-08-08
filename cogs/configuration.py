import discord
from discord import app_commands
from discord.ext import commands
from database import set_guild_config, get_guild_config
from utils.embeds import build_embed, error_embed, format_duration
from utils.duration import parse_duration


class Configuration(commands.Cog):
    """
    Server-level jail system configuration. Grouped under /jailconfig (see
    naming note in sentence.py). /jailconfig autorestore has been removed
    per spec; the underlying auto_restore config value is still read by
    release_member() in utils/jail_actions.py, it just can no longer be
    toggled via a command.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    jailconfig = app_commands.Group(name="jailconfig", description="Configure the jail system.",
                                     default_permissions=discord.Permissions(administrator=True))

    @jailconfig.command(name="role", description="Set jail role.")
    @app_commands.describe(role="The role used to mark jailed members")
    async def role(self, interaction: discord.Interaction, role: discord.Role):
        await set_guild_config(interaction.guild.id, jail_role_id=role.id)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Jail role set to {role.mention}."))

    @jailconfig.command(name="logchannel", description="Set log channel.")
    @app_commands.describe(channel="Channel where jail actions are logged")
    async def logchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await set_guild_config(interaction.guild.id, log_channel_id=channel.id)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Log channel set to {channel.mention}."))

    @jailconfig.command(name="appealchannel", description="Set appeal channel.")
    @app_commands.describe(channel="Channel where appeals are posted")
    async def appealchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await set_guild_config(interaction.guild.id, appeal_channel_id=channel.id)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Appeal channel set to {channel.mention}."))

    @jailconfig.command(name="category", description="Set jail category.")
    @app_commands.describe(category="Category that holds the jail channels")
    async def category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await set_guild_config(interaction.guild.id, jail_category_id=category.id)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Jail category set to {category.name}."))

    @jailconfig.command(name="defaulttime", description="Set default jail duration.")
    @app_commands.describe(duration="Default sentence length, e.g. 30s, 10m, 2hr, 1d")
    async def defaulttime(self, interaction: discord.Interaction, duration: str):
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.response.send_message(embed=error_embed(str(exc)))
        await set_guild_config(interaction.guild.id, default_seconds=seconds)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Default jail duration set to {format_duration(seconds)}."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Configuration(bot))
