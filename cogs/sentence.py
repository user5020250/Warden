import discord
from discord import app_commands
from discord.ext import commands

from database import db, now
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import trusted_only
from utils.jail_actions import release_member


async def _active_case(guild_id: int, member: discord.Member):
    cur = await db().execute(
        "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active'"
        " ORDER BY created_at DESC LIMIT 1",
        (guild_id, member.id),
    )
    return await cur.fetchone()


class Sentence(commands.Cog):
    """
    Sentence management. Grouped under /sentence rather than /jail because
    Discord does not allow a command and a subcommand group to share the
    same name, and /jail is already the direct jailing action.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    sentence = app_commands.Group(name="sentence", description="Manage an active jail sentence.")

    @sentence.command(name="extend", description="Add more jail time.")
    @app_commands.describe(member="The jailed member", minutes="Minutes to add")
    @trusted_only()
    async def extend(self, interaction: discord.Interaction, member: discord.Member, minutes: int):
        await interaction.response.defer()
        case = await _active_case(interaction.guild.id, member)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if case["duration_seconds"] is None:
            return await interaction.followup.send(embed=error_embed("That sentence is already permanent."))
        elapsed = now() - case["created_at"]
        remaining = max(0, case["duration_seconds"] - elapsed)
        new_remaining = remaining + minutes * 60
        new_duration = elapsed + new_remaining
        await db().execute("UPDATE jail_cases SET duration_seconds = ? WHERE case_id = ?",
                            (new_duration, case["case_id"]))
        await db().commit()
        await interaction.followup.send(embed=build_embed(
            "Sentence Extended",
            f"Case #{case['case_id']} extended by {minutes} minute(s). New time remaining: {format_duration(new_remaining)}."
        ))

    @sentence.command(name="reduce", description="Reduce jail time.")
    @app_commands.describe(member="The jailed member", minutes="Minutes to remove")
    @trusted_only()
    async def reduce(self, interaction: discord.Interaction, member: discord.Member, minutes: int):
        await interaction.response.defer()
        case = await _active_case(interaction.guild.id, member)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if case["duration_seconds"] is None:
            return await interaction.followup.send(embed=error_embed(
                "That sentence is permanent; use /sentence settime to give it a fixed length first."))
        elapsed = now() - case["created_at"]
        remaining = max(0, case["duration_seconds"] - elapsed)
        new_remaining = max(0, remaining - minutes * 60)
        new_duration = elapsed + new_remaining
        await db().execute("UPDATE jail_cases SET duration_seconds = ? WHERE case_id = ?",
                            (new_duration, case["case_id"]))
        await db().commit()
        if new_remaining <= 0:
            success, message = await release_member(interaction.guild, member, interaction.user,
                                                      case["case_id"], "released", self.bot)
            return await interaction.followup.send(embed=build_embed("Sentence Reduced", "Sentence reached zero — " + message))
        await interaction.followup.send(embed=build_embed(
            "Sentence Reduced",
            f"Case #{case['case_id']} reduced by {minutes} minute(s). New time remaining: {format_duration(new_remaining)}."
        ))

    @sentence.command(name="settime", description="Replace the remaining sentence.")
    @app_commands.describe(member="The jailed member", minutes="New total minutes remaining")
    @trusted_only()
    async def settime(self, interaction: discord.Interaction, member: discord.Member, minutes: int):
        await interaction.response.defer()
        case = await _active_case(interaction.guild.id, member)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        elapsed = now() - case["created_at"]
        new_duration = elapsed + max(0, minutes * 60)
        await db().execute("UPDATE jail_cases SET duration_seconds = ? WHERE case_id = ?",
                            (new_duration, case["case_id"]))
        await db().commit()
        await interaction.followup.send(embed=build_embed(
            "Sentence Updated", f"Case #{case['case_id']} time remaining set to {minutes} minute(s)."))

    @sentence.command(name="permanent", description="Convert to permanent jail.")
    @app_commands.describe(member="The jailed member")
    @trusted_only()
    async def permanent(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        case = await _active_case(interaction.guild.id, member)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        await db().execute("UPDATE jail_cases SET duration_seconds = NULL WHERE case_id = ?", (case["case_id"],))
        await db().commit()
        await interaction.followup.send(embed=build_embed(
            "Sentence Updated", f"Case #{case['case_id']} is now permanent until manually released."))

    @sentence.command(name="pardon", description="Completely forgive a user's sentence.")
    @app_commands.describe(member="The jailed member")
    @trusted_only()
    async def pardon(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        case = await _active_case(interaction.guild.id, member)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        success, message = await release_member(interaction.guild, member, interaction.user,
                                                  case["case_id"], "pardoned", self.bot)
        await interaction.followup.send(embed=build_embed("Pardon", message) if success else error_embed(message))

    @sentence.command(name="freeze", description="Pause the jail timer.")
    @app_commands.describe(member="The jailed member")
    @trusted_only()
    async def freeze(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        case = await _active_case(interaction.guild.id, member)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if case["frozen"]:
            return await interaction.followup.send(embed=error_embed("That sentence is already frozen."))
        if case["duration_seconds"] is None:
            return await interaction.followup.send(embed=error_embed("Permanent sentences can't be frozen."))
        elapsed = now() - case["created_at"]
        remaining = max(0, case["duration_seconds"] - elapsed)
        await db().execute(
            "UPDATE jail_cases SET frozen = 1, remaining_seconds = ? WHERE case_id = ?",
            (remaining, case["case_id"]),
        )
        await db().commit()
        await interaction.followup.send(embed=build_embed(
            "Sentence Frozen", f"Case #{case['case_id']} paused with {format_duration(remaining)} remaining."))

    @sentence.command(name="resume", description="Resume a paused sentence.")
    @app_commands.describe(member="The jailed member")
    @trusted_only()
    async def resume(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        case = await _active_case(interaction.guild.id, member)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if not case["frozen"]:
            return await interaction.followup.send(embed=error_embed("That sentence is not frozen."))
        new_duration = case["remaining_seconds"]
        await db().execute(
            "UPDATE jail_cases SET frozen = 0, created_at = ?, duration_seconds = ? WHERE case_id = ?",
            (now(), new_duration, case["case_id"]),
        )
        await db().commit()
        await interaction.followup.send(embed=build_embed(
            "Sentence Resumed", f"Case #{case['case_id']} resumed with {format_duration(new_duration)} remaining."))

    @sentence.command(name="restart", description="Restart the timer from the beginning.")
    @app_commands.describe(member="The jailed member")
    @trusted_only()
    async def restart(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        case = await _active_case(interaction.guild.id, member)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        original = case["remaining_seconds"] if case["frozen"] else case["duration_seconds"]
        await db().execute(
            "UPDATE jail_cases SET created_at = ?, frozen = 0, duration_seconds = ? WHERE case_id = ?",
            (now(), original, case["case_id"]),
        )
        await db().commit()
        await interaction.followup.send(embed=build_embed(
            "Sentence Restarted", f"Case #{case['case_id']} timer restarted from the beginning."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Sentence(bot))
