import discord
from discord import app_commands
from discord.ext import commands

from database import set_guild_config, get_guild_config
from utils.embeds import build_embed, error_embed


class Configuration(commands.Cog):
    """Server-level jail system configuration. Grouped under /jailconfig (see naming note in sentence.py)."""

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
    @app_commands.describe(minutes="Default sentence length in minutes")
    async def defaulttime(self, interaction: discord.Interaction, minutes: int):
        await set_guild_config(interaction.guild.id, default_minutes=minutes)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Default jail duration set to {minutes} minute(s)."))

    @jailconfig.command(name="dm", description="Toggle DM notifications.")
    @app_commands.describe(enabled="Whether jailed members should be DMed")
    async def dm(self, interaction: discord.Interaction, enabled: bool):
        await set_guild_config(interaction.guild.id, dm_notifications=int(enabled))
        await interaction.response.send_message(embed=build_embed("Config Updated", f"DM notifications {'enabled' if enabled else 'disabled'}."))

    @jailconfig.command(name="autorestore", description="Toggle automatic role restoration.")
    @app_commands.describe(enabled="Whether roles should be restored automatically on release")
    async def autorestore(self, interaction: discord.Interaction, enabled: bool):
        await set_guild_config(interaction.guild.id, auto_restore=int(enabled))
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Automatic role restoration {'enabled' if enabled else 'disabled'}."))

    @jailconfig.command(name="voicemode", description="Configure voice behavior for jailed members.")
    @app_commands.describe(mode="How to treat jailed members who are in voice channels")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Do nothing", value="none"),
        app_commands.Choice(name="Deafen while jailed", value="deafen"),
    ])
    async def voicemode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await set_guild_config(interaction.guild.id, voice_mode=mode.value)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"Voice mode set to: {mode.name}."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Configuration(bot))
