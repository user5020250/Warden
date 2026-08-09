import discord
from discord import app_commands
from discord.ext import commands

from database import db, get_guild_config, set_guild_config
from utils.embeds import build_embed, error_embed, format_duration
from utils.duration import parse_duration
from utils.permissions import staff_only, is_staff

# Naming note: the spec has "/autojail" both as a standalone command (opens
# a panel) and as a group of subcommands (settings, threshold, window,
# duration, whitelist add/remove) — the same standalone-vs-group conflict
# handled elsewhere in this bot. "/autojail" keeps the panel, and the
# configuration subcommands move to their own group, "/autojailconfig".


class AutoJailPanel(discord.ui.View):
    """Persistent Enable/Disable panel posted by /autojail."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enable", style=discord.ButtonStyle.success, custom_id="autojail_enable")
    async def enable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set(interaction, True)

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger, custom_id="autojail_disable")
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set(interaction, False)

    async def _set(self, interaction: discord.Interaction, enabled: bool):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            return await interaction.response.send_message(embed=error_embed("You do not have permission to change this."), ephemeral=True)
        await set_guild_config(interaction.guild.id, autojail_enabled=int(enabled))
        cfg = await get_guild_config(interaction.guild.id)
        embed = _panel_embed(cfg, changed_by=interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)


def _panel_embed(cfg, changed_by: discord.abc.User = None) -> discord.Embed:
    status = "Enabled" if cfg["autojail_enabled"] else "Disabled"
    fields = [
        ("Status", f"`{status}`", True),
        ("Threshold", f"`{cfg['autojail_threshold']}` messages", True),
        ("Window", f"`{format_duration(cfg['autojail_window_seconds'])}`", True),
        ("Jail Duration", f"`{format_duration(cfg['autojail_duration_seconds'])}`", True),
    ]
    if changed_by is not None:
        fields.append(("Changed By", changed_by.mention, True))
    return build_embed(
        "AutoJail",
        "Automatically jails members who send messages faster than the configured threshold. "
        "Use the buttons below to enable or disable it, or `/autojailconfig` to change the threshold, "
        "window, or jail duration.",
        fields=fields,
    )


class AutoJail(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(AutoJailPanel())

    autojailconfig = app_commands.Group(name="autojailconfig", description="Configure AutoJail.",
                                         default_permissions=discord.Permissions(administrator=True))
    whitelist = app_commands.Group(name="whitelist", description="Manage the AutoJail whitelist.", parent=autojailconfig)

    @app_commands.command(name="autojail", description="Opens the AutoJail enable/disable panel.")
    @staff_only()
    async def autojail(self, interaction: discord.Interaction):
        cfg = await get_guild_config(interaction.guild.id)
        await interaction.response.send_message(embed=_panel_embed(cfg), view=AutoJailPanel())

    @autojailconfig.command(name="settings", description="Shows the current AutoJail configuration.")
    async def settings(self, interaction: discord.Interaction):
        cfg = await get_guild_config(interaction.guild.id)
        await interaction.response.send_message(embed=_panel_embed(cfg))

    @autojailconfig.command(name="threshold", description="Sets how many violations trigger AutoJail.")
    @app_commands.describe(number="Number of messages within the window that triggers AutoJail")
    async def threshold(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 100]):
        await set_guild_config(interaction.guild.id, autojail_threshold=number)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"AutoJail threshold set to `{number}` messages."))

    @autojailconfig.command(name="window", description="Sets the period in which violations are counted.")
    @app_commands.describe(duration="Time window, e.g. 30s, 1m, 2m")
    async def window(self, interaction: discord.Interaction, duration: str):
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.response.send_message(embed=error_embed(str(exc)))
        if seconds is None:
            return await interaction.response.send_message(embed=error_embed("The window cannot be permanent."))
        await set_guild_config(interaction.guild.id, autojail_window_seconds=seconds)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"AutoJail window set to `{format_duration(seconds)}`."))

    @autojailconfig.command(name="duration", description="Sets the jail duration applied by AutoJail.")
    @app_commands.describe(duration="Sentence length, e.g. 10m, 2hr, 1d, or permanent")
    async def duration(self, interaction: discord.Interaction, duration: str):
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.response.send_message(embed=error_embed(str(exc)))
        await set_guild_config(interaction.guild.id, autojail_duration_seconds=seconds)
        await interaction.response.send_message(embed=build_embed("Config Updated", f"AutoJail jail duration set to `{format_duration(seconds)}`."))

    @whitelist.command(name="add", description="Prevents a member from being automatically jailed.")
    @app_commands.describe(member="The member to whitelist")
    async def whitelist_add(self, interaction: discord.Interaction, member: discord.Member):
        await db().execute(
            "INSERT OR IGNORE INTO autojail_whitelist (guild_id, user_id) VALUES (?, ?)",
            (interaction.guild.id, member.id),
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Whitelist Updated", f"{member.mention} is now exempt from AutoJail."))

    @whitelist.command(name="remove", description="Removes a member from the AutoJail whitelist.")
    @app_commands.describe(member="The member to remove from the whitelist")
    async def whitelist_remove(self, interaction: discord.Interaction, member: discord.Member):
        await db().execute(
            "DELETE FROM autojail_whitelist WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id)
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Whitelist Updated", f"{member.mention} has been removed from the AutoJail whitelist."))


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoJail(bot))
