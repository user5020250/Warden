import time
import discord
from discord import app_commands
from discord.ext import commands

from database import db, get_guild_config
from utils.embeds import build_embed, error_embed
from utils.permissions import trusted_only, is_exempt
from utils.jail_actions import jail_member

# Simple in-memory violation tracker: {(guild_id, user_id): [timestamps]}
_violations: dict[tuple[int, int], list[float]] = {}

# A conservative, easily-editable default word filter. Server staff are
# expected to tune this to their community; this is intentionally minimal.
DEFAULT_BANNED_WORDS = {"slur_placeholder_1", "slur_placeholder_2"}


async def _get_autojail_config(guild_id: int):
    cur = await db().execute("SELECT * FROM autojail_config WHERE guild_id = ?", (guild_id,))
    row = await cur.fetchone()
    if row is None:
        await db().execute("INSERT INTO autojail_config (guild_id) VALUES (?)", (guild_id,))
        await db().commit()
        cur = await db().execute("SELECT * FROM autojail_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
    return row


class AutoJail(commands.Cog):
    """
    Real-time violation detection: rapid message spam within a rolling
    window, and a basic banned-word filter. When a member crosses the
    configured violation threshold they are jailed automatically.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    autojail = app_commands.Group(name="autojail", description="Configure automatic jailing.")

    @autojail.command(name="enable", description="Enable automatic jail.")
    @trusted_only()
    async def enable(self, interaction: discord.Interaction):
        await _get_autojail_config(interaction.guild.id)
        await db().execute("UPDATE autojail_config SET enabled = 1 WHERE guild_id = ?", (interaction.guild.id,))
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Autojail Enabled", "Automatic jailing is now active."))

    @autojail.command(name="disable", description="Disable automatic jail.")
    @trusted_only()
    async def disable(self, interaction: discord.Interaction):
        await _get_autojail_config(interaction.guild.id)
        await db().execute("UPDATE autojail_config SET enabled = 0 WHERE guild_id = ?", (interaction.guild.id,))
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Autojail Disabled", "Automatic jailing is now off."))

    @autojail.command(name="violations", description="Configure violation triggers.")
    @app_commands.describe(max_violations="Violations allowed before auto-jail", window_seconds="Rolling window in seconds")
    @trusted_only()
    async def violations(self, interaction: discord.Interaction, max_violations: int, window_seconds: int):
        await _get_autojail_config(interaction.guild.id)
        await db().execute(
            "UPDATE autojail_config SET max_violations = ?, window_seconds = ? WHERE guild_id = ?",
            (max_violations, window_seconds, interaction.guild.id),
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed(
            "Autojail Updated", f"Threshold set to {max_violations} violation(s) per {window_seconds}s."))

    @autojail.command(name="whitelist", description="Ignore certain roles/users for autojail.")
    @app_commands.describe(target="Role or user to whitelist")
    @trusted_only()
    async def whitelist(self, interaction: discord.Interaction, target: discord.Role | discord.Member):
        await db().execute(
            "INSERT OR IGNORE INTO autojail_lists (guild_id, entity_id, list_type) VALUES (?, ?, 'whitelist')",
            (interaction.guild.id, target.id),
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Whitelisted", f"{target.mention} will be ignored by autojail."))

    @autojail.command(name="blacklist", description="Always jail certain users on their next violation.")
    @app_commands.describe(target="Role or user to blacklist")
    @trusted_only()
    async def blacklist(self, interaction: discord.Interaction, target: discord.Role | discord.Member):
        await db().execute(
            "INSERT OR IGNORE INTO autojail_lists (guild_id, entity_id, list_type) VALUES (?, ?, 'blacklist')",
            (interaction.guild.id, target.id),
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed(
            "Blacklisted", f"{target.mention} will be auto-jailed immediately on their next violation."))

    @autojail.command(name="duration", description="Default sentence length for autojail.")
    @app_commands.describe(minutes="Minutes to jail for on an automatic trigger")
    @trusted_only()
    async def duration(self, interaction: discord.Interaction, minutes: int):
        await _get_autojail_config(interaction.guild.id)
        await db().execute("UPDATE autojail_config SET default_minutes = ? WHERE guild_id = ?",
                            (minutes, interaction.guild.id))
        await db().commit()
        await interaction.response.send_message(embed=build_embed(
            "Autojail Updated", f"Automatic jail sentences are now {minutes} minute(s)."))

    # ------------------------------------------------------------------
    # Real-time detection
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        cfg = await _get_autojail_config(message.guild.id)
        if not cfg["enabled"]:
            return
        member = message.author
        if not isinstance(member, discord.Member):
            return
        if await is_exempt(member):
            return

        role_ids = [r.id for r in member.roles]
        placeholders = ",".join(["?"] * (len(role_ids) + 1))

        cur = await db().execute(
            f"SELECT 1 FROM autojail_lists WHERE guild_id = ? AND list_type = 'whitelist' AND entity_id IN ({placeholders})",
            (message.guild.id, member.id, *role_ids),
        )
        if await cur.fetchone():
            return

        cur = await db().execute(
            f"SELECT 1 FROM autojail_lists WHERE guild_id = ? AND list_type = 'blacklist' AND entity_id IN ({placeholders})",
            (message.guild.id, member.id, *role_ids),
        )
        blacklisted = await cur.fetchone() is not None

        triggered = blacklisted or self._is_spam(message.guild.id, member.id, cfg) or self._has_banned_word(message.content)
        if not triggered:
            return

        success, msg, case_id = await jail_member(
            message.guild, member, message.guild.me, "Automatic jail: violation threshold reached",
            cfg["default_minutes"] * 60, self.bot,
        )
        if success:
            try:
                await message.channel.send(embed=build_embed("Autojail Triggered", msg))
            except discord.Forbidden:
                pass

    def _is_spam(self, guild_id: int, user_id: int, cfg) -> bool:
        key = (guild_id, user_id)
        window = cfg["window_seconds"]
        threshold = cfg["max_violations"]
        now_ts = time.time()
        history = _violations.setdefault(key, [])
        history.append(now_ts)
        _violations[key] = [t for t in history if now_ts - t <= window]
        return len(_violations[key]) >= threshold

    def _has_banned_word(self, content: str) -> bool:
        lowered = content.lower()
        return any(word in lowered for word in DEFAULT_BANNED_WORDS)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoJail(bot))
