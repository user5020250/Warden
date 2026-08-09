import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_guild_config, get_active_case
from utils.embeds import build_embed, error_embed, format_duration
from utils.duration import parse_duration
from utils.permissions import staff_only
from utils.notify import notify_and_log
from utils.jail_actions import jail_member, release_member
from utils.pagination import Paginator


def _remaining_seconds(case) -> int | None:
    if case["duration_seconds"] is None:
        return None
    return max(0, case["created_at"] + case["duration_seconds"] - now())


class Jail(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="jail", description="Jails a member, assigns the jail role, and opens a case.")
    @app_commands.describe(
        member="The member to jail",
        duration="Sentence length, e.g. 30s, 10m, 2hr, 1d, or permanent (defaults to the server default)",
        reason="Why this member is being jailed",
    )
    @staff_only()
    async def jail(self, interaction: discord.Interaction, member: discord.Member, duration: str = None, reason: str = None):
        await interaction.response.defer()

        if member.id == interaction.user.id:
            return await interaction.followup.send(embed=error_embed("You cannot jail yourself."))
        if member.bot:
            return await interaction.followup.send(embed=error_embed("You cannot jail a bot."))
        if member.id == interaction.guild.owner_id:
            return await interaction.followup.send(embed=error_embed("You cannot jail the server owner."))

        existing = await get_active_case(interaction.guild.id, member.id)
        if existing is not None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is already jailed under case `#{existing['case_id']}`."))

        cfg = await get_guild_config(interaction.guild.id)
        if duration:
            try:
                seconds = parse_duration(duration)
            except ValueError as exc:
                return await interaction.followup.send(embed=error_embed(str(exc)))
        else:
            seconds = cfg["default_seconds"]

        success, message, case_id = await jail_member(interaction.guild, member, interaction.user, reason, seconds)
        if not success:
            return await interaction.followup.send(embed=error_embed(message))

        await notify_and_log(
            interaction.guild,
            action="jail",
            user_id=member.id,
            moderator_id=interaction.user.id,
            case_id=case_id,
            detail=reason,
            cfg=cfg,
            dm_target=member,
            dm_title="You Have Been Jailed",
            dm_fields=[
                ("Server", interaction.guild.name, True),
                ("Case ID", f"`#{case_id}`", True),
                ("Duration", f"`{format_duration(seconds)}`", True),
                ("Reason", reason or "No reason provided", False),
            ],
            log_title="Member Jailed",
            log_fields=[
                ("Member", f"{member.mention} (`{member.id}`)", True),
                ("Moderator", interaction.user.mention, True),
                ("Case ID", f"`#{case_id}`", True),
                ("Duration", f"`{format_duration(seconds)}`", True),
                ("Reason", reason or "No reason provided", False),
            ],
        )

        await interaction.followup.send(embed=build_embed(
            "Member Jailed",
            None,
            fields=[
                ("Member", member.mention, True),
                ("Case ID", f"`#{case_id}`", True),
                ("Duration", f"`{format_duration(seconds)}`", True),
                ("Reason", reason or "No reason provided", False),
            ],
        ))

    @app_commands.command(name="unjail", description="Releases a jailed member and restores their previous roles.")
    @app_commands.describe(member="The jailed member to release")
    @staff_only()
    async def unjail(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()

        case = await get_active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))

        success, message = await release_member(interaction.guild, member, interaction.user, case["case_id"], "released")
        if not success:
            return await interaction.followup.send(embed=error_embed(message))

        await notify_and_log(
            interaction.guild,
            action="unjail",
            user_id=member.id,
            moderator_id=interaction.user.id,
            case_id=case["case_id"],
            dm_target=member,
            dm_title="You Have Been Released",
            dm_fields=[
                ("Server", interaction.guild.name, True),
                ("Case ID", f"`#{case['case_id']}`", True),
            ],
            log_title="Member Released",
            log_fields=[
                ("Member", f"{member.mention} (`{member.id}`)", True),
                ("Moderator", interaction.user.mention, True),
                ("Case ID", f"`#{case['case_id']}`", True),
            ],
        )

        await interaction.followup.send(embed=build_embed(
            "Member Released", f"{member.mention} has been released and case `#{case['case_id']}` is now closed."
        ))

    @app_commands.command(name="jailstatus", description="Shows all currently jailed members and their remaining sentence.")
    @staff_only()
    async def jailstatus(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND status = 'active' ORDER BY created_at ASC",
            (interaction.guild.id,),
        )
        cases = await cur.fetchall()
        lines = []
        for case in cases:
            remaining = _remaining_seconds(case)
            remaining_text = "Permanent" if remaining is None else format_duration(remaining)
            lines.append(f"`#{case['case_id']}` — <@{case['user_id']}> — Remaining: `{remaining_text}` — {case['reason'] or 'No reason provided'}")
        view = Paginator("Currently Jailed", lines, "No members are currently jailed.")
        await interaction.followup.send(embed=view.render(), view=view)

    @app_commands.command(name="jailinfo", description="Shows a member's current jail status, sentence, reason, cell, and case information.")
    @app_commands.describe(member="The member to look up")
    @staff_only()
    async def jailinfo(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        case = await get_active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.followup.send(embed=build_embed("Jail Info", f"{member.mention} is not currently jailed."))

        remaining = _remaining_seconds(case)
        remaining_text = "Permanent" if remaining is None else format_duration(remaining)
        cell = interaction.guild.get_channel(case["cell_channel_id"]) if case["cell_channel_id"] else None

        embed = build_embed(
            f"Jail Info — {member}",
            None,
            fields=[
                ("Case ID", f"`#{case['case_id']}`", True),
                ("Moderator", f"<@{case['moderator_id']}>", True),
                ("Remaining", f"`{remaining_text}`", True),
                ("Cell", cell.mention if cell else "None", True),
                ("Jailed Since", f"<t:{case['created_at']}:F>", True),
                ("Reason", case["reason"] or "No reason provided", False),
            ],
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Jail(bot))
