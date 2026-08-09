import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_active_case
from utils.embeds import build_embed, error_embed, format_duration
from utils.duration import parse_duration
from utils.permissions import staff_only
from utils.notify import notify_and_log
from utils.jail_actions import release_member


def _remaining_seconds(case) -> int | None:
    if case["duration_seconds"] is None:
        return None
    return max(0, case["created_at"] + case["duration_seconds"] - now())


class Sentence(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    sentence = app_commands.Group(name="sentence", description="View or change an active jail sentence.")

    @sentence.command(name="view", description="Shows your current sentence and remaining time.")
    async def view(self, interaction: discord.Interaction):
        case = await get_active_case(interaction.guild.id, interaction.user.id)
        if case is None:
            return await interaction.response.send_message(embed=error_embed("You are not currently jailed."), ephemeral=True)
        remaining = _remaining_seconds(case)
        remaining_text = "Permanent" if remaining is None else format_duration(remaining)
        embed = build_embed(
            "Your Sentence",
            None,
            fields=[
                ("Case ID", f"`#{case['case_id']}`", True),
                ("Remaining", f"`{remaining_text}`", True),
                ("Reason", case["reason"] or "No reason provided", False),
            ],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @sentence.command(name="set", description="Changes the member's sentence to a specific duration.")
    @app_commands.describe(member="The jailed member", duration="New total duration, e.g. 30s, 10m, 2hr, 1d, or permanent")
    @staff_only()
    async def set(self, interaction: discord.Interaction, member: discord.Member, duration: str):
        await interaction.response.defer()
        case = await get_active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.followup.send(embed=error_embed(str(exc)))

        await db().execute(
            "UPDATE jail_cases SET duration_seconds = ?, created_at = ? WHERE guild_id = ? AND case_id = ?",
            (seconds, now(), interaction.guild.id, case["case_id"]),
        )
        await db().commit()

        await notify_and_log(
            interaction.guild, action="sentence_set", user_id=member.id, moderator_id=interaction.user.id,
            case_id=case["case_id"], detail=f"Set to {format_duration(seconds)}",
            log_title="Sentence Updated",
            log_fields=[
                ("Member", member.mention, True),
                ("Moderator", interaction.user.mention, True),
                ("Case ID", f"`#{case['case_id']}`", True),
                ("New Duration", f"`{format_duration(seconds)}`", True),
            ],
        )
        await interaction.followup.send(embed=build_embed(
            "Sentence Updated", f"Case `#{case['case_id']}` for {member.mention} is now set to `{format_duration(seconds)}` remaining."
        ))

    @sentence.command(name="extend", description="Adds additional time to an active sentence.")
    @app_commands.describe(member="The jailed member", duration="Time to add, e.g. 30s, 10m, 2hr, 1d")
    @staff_only()
    async def extend(self, interaction: discord.Interaction, member: discord.Member, duration: str):
        await interaction.response.defer()
        case = await get_active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if case["duration_seconds"] is None:
            return await interaction.followup.send(embed=error_embed("This case is permanent and cannot be extended by a fixed amount."))
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.followup.send(embed=error_embed(str(exc)))
        if seconds is None:
            return await interaction.followup.send(embed=error_embed("Use `/sentence set` to change a case to permanent."))

        new_total = case["duration_seconds"] + seconds
        await db().execute(
            "UPDATE jail_cases SET duration_seconds = ? WHERE guild_id = ? AND case_id = ?",
            (new_total, interaction.guild.id, case["case_id"]),
        )
        await db().commit()

        await notify_and_log(
            interaction.guild, action="sentence_extend", user_id=member.id, moderator_id=interaction.user.id,
            case_id=case["case_id"], detail=f"Extended by {format_duration(seconds)}",
            log_title="Sentence Extended",
            log_fields=[
                ("Member", member.mention, True),
                ("Moderator", interaction.user.mention, True),
                ("Case ID", f"`#{case['case_id']}`", True),
                ("Added", f"`{format_duration(seconds)}`", True),
            ],
        )
        remaining = max(0, case["created_at"] + new_total - now())
        await interaction.followup.send(embed=build_embed(
            "Sentence Extended",
            f"Case `#{case['case_id']}` for {member.mention} extended by `{format_duration(seconds)}`. "
            f"Remaining: `{format_duration(remaining)}`.",
        ))

    @sentence.command(name="reduce", description="Removes time from an active sentence.")
    @app_commands.describe(member="The jailed member", duration="Time to remove, e.g. 30s, 10m, 2hr, 1d")
    @staff_only()
    async def reduce(self, interaction: discord.Interaction, member: discord.Member, duration: str):
        await interaction.response.defer()
        case = await get_active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        if case["duration_seconds"] is None:
            return await interaction.followup.send(embed=error_embed("This case is permanent and cannot be reduced by a fixed amount."))
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            return await interaction.followup.send(embed=error_embed(str(exc)))
        if seconds is None:
            return await interaction.followup.send(embed=error_embed("Use `/sentence set` to change a case to permanent."))

        new_total = case["duration_seconds"] - seconds
        remaining = case["created_at"] + new_total - now()

        if remaining <= 0:
            success, message = await release_member(interaction.guild, member, interaction.user, case["case_id"], "released")
            if not success:
                return await interaction.followup.send(embed=error_embed(message))
            await notify_and_log(
                interaction.guild, action="sentence_reduce_release", user_id=member.id, moderator_id=interaction.user.id,
                case_id=case["case_id"], detail="Reduction brought remaining time to zero; member released",
                dm_target=member, dm_title="You Have Been Released",
                dm_fields=[("Server", interaction.guild.name, True), ("Case ID", f"`#{case['case_id']}`", True)],
                log_title="Member Released", log_fields=[
                    ("Member", f"{member.mention} (`{member.id}`)", True),
                    ("Moderator", interaction.user.mention, True),
                    ("Case ID", f"`#{case['case_id']}`", True),
                ],
            )
            return await interaction.followup.send(embed=build_embed(
                "Sentence Reduced", f"The reduction brought case `#{case['case_id']}` to zero remaining time, so {member.mention} has been released."
            ))

        await db().execute(
            "UPDATE jail_cases SET duration_seconds = ? WHERE guild_id = ? AND case_id = ?",
            (new_total, interaction.guild.id, case["case_id"]),
        )
        await db().commit()

        await notify_and_log(
            interaction.guild, action="sentence_reduce", user_id=member.id, moderator_id=interaction.user.id,
            case_id=case["case_id"], detail=f"Reduced by {format_duration(seconds)}",
            log_title="Sentence Reduced",
            log_fields=[
                ("Member", member.mention, True),
                ("Moderator", interaction.user.mention, True),
                ("Case ID", f"`#{case['case_id']}`", True),
                ("Removed", f"`{format_duration(seconds)}`", True),
            ],
        )
        await interaction.followup.send(embed=build_embed(
            "Sentence Reduced",
            f"Case `#{case['case_id']}` for {member.mention} reduced by `{format_duration(seconds)}`. "
            f"Remaining: `{format_duration(remaining)}`.",
        ))

    @sentence.command(name="end", description="Immediately ends the member's sentence and releases them.")
    @app_commands.describe(member="The jailed member")
    @staff_only()
    async def end(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        case = await get_active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))

        success, message = await release_member(interaction.guild, member, interaction.user, case["case_id"], "released")
        if not success:
            return await interaction.followup.send(embed=error_embed(message))

        await notify_and_log(
            interaction.guild, action="sentence_end", user_id=member.id, moderator_id=interaction.user.id,
            case_id=case["case_id"],
            dm_target=member, dm_title="You Have Been Released",
            dm_fields=[("Server", interaction.guild.name, True), ("Case ID", f"`#{case['case_id']}`", True)],
            log_title="Member Released",
            log_fields=[
                ("Member", f"{member.mention} (`{member.id}`)", True),
                ("Moderator", interaction.user.mention, True),
                ("Case ID", f"`#{case['case_id']}`", True),
            ],
        )
        await interaction.followup.send(embed=build_embed(
            "Sentence Ended", f"Case `#{case['case_id']}` for {member.mention} has been ended and they've been released."
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Sentence(bot))
