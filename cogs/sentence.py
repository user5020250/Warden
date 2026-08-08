import discord
from discord import app_commands
from discord.ext import commands

from database import db, now
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import trusted_only
from utils.jail_actions import release_member
from utils.duration import parse_duration
from utils.notify import notify_and_log


async def _active_case(guild_id: int, user_id: int):
    cur = await db().execute(
        "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active'"
        " ORDER BY created_at DESC LIMIT 1",
        (guild_id, user_id),
    )
    return await cur.fetchone()


class DurationModal(discord.ui.Modal):
    """Shared modal for Extend / Reduce / Set Time — all just need one duration string."""

    duration = discord.ui.TextInput(
        label="Duration", placeholder="e.g. 30s, 10m, 2hr, 1d", max_length=32,
    )

    def __init__(self, title: str, member: discord.Member, action: str, bot: commands.Bot,
                 allow_permanent: bool = False):
        super().__init__(title=title)
        self.member = member
        self.action = action
        self.bot = bot
        self.allow_permanent = allow_permanent
        if allow_permanent:
            self.duration.placeholder = "e.g. 30s, 10m, 2hr, 1d, or permanent"

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            seconds = parse_duration(self.duration.value, allow_permanent=self.allow_permanent)
        except ValueError as exc:
            return await interaction.followup.send(embed=error_embed(str(exc)), ephemeral=True)

        case = await _active_case(interaction.guild.id, self.member.id)
        if case is None:
            return await interaction.followup.send(
                embed=error_embed(f"{self.member.mention} is not currently jailed."), ephemeral=True)

        if self.action == "extend":
            if case["duration_seconds"] is None:
                return await interaction.followup.send(embed=error_embed("That sentence is already permanent."), ephemeral=True)
            elapsed = now() - case["created_at"]
            remaining = max(0, case["duration_seconds"] - elapsed)
            new_remaining = remaining + seconds
            new_duration = elapsed + new_remaining
            await db().execute("UPDATE jail_cases SET duration_seconds = ? WHERE guild_id = ? AND case_id = ? AND status = 'active'",
                                (new_duration, interaction.guild.id, case["case_id"]))
            await db().commit()
            await notify_and_log(
                interaction.guild,
                action="sentence_extend",
                user_id=self.member.id,
                moderator_id=interaction.user.id,
                case_id=case["case_id"],
                detail=f"Extended by {format_duration(seconds)}",
                dm_target=self.member,
                dm_title="Your Sentence Has Been Extended",
                dm_fields=[
                    ("Case ID", f"#{case['case_id']}", True),
                    ("Extended By", format_duration(seconds), True),
                    ("Time Remaining", format_duration(new_remaining), True),
                ],
                log_title="Sentence Extended",
                log_fields=[
                    ("Member", f"{self.member.mention} ({self.member.id})", True),
                    ("Moderator", interaction.user.mention, True),
                    ("Case ID", f"#{case['case_id']}", True),
                    ("Extended By", format_duration(seconds), True),
                    ("Time Remaining", format_duration(new_remaining), True),
                ],
            )
            return await interaction.followup.send(embed=build_embed(
                "Sentence Extended",
                f"Case #{case['case_id']} extended by {format_duration(seconds)}. New time remaining: {format_duration(new_remaining)}."
            ), ephemeral=True)

        if self.action == "reduce":
            if case["duration_seconds"] is None:
                return await interaction.followup.send(embed=error_embed(
                    "That sentence is permanent; use Set Time to give it a fixed length first."), ephemeral=True)
            elapsed = now() - case["created_at"]
            remaining = max(0, case["duration_seconds"] - elapsed)
            new_remaining = max(0, remaining - seconds)
            new_duration = elapsed + new_remaining
            await db().execute("UPDATE jail_cases SET duration_seconds = ? WHERE guild_id = ? AND case_id = ? AND status = 'active'",
                                (new_duration, interaction.guild.id, case["case_id"]))
            await db().commit()
            if new_remaining <= 0:
                success, message = await release_member(interaction.guild, self.member, interaction.user,
                                                          case["case_id"], "released", self.bot)
                return await interaction.followup.send(embed=build_embed(
                    "Sentence Reduced", "Sentence reached zero — " + message), ephemeral=True)
            await notify_and_log(
                interaction.guild,
                action="sentence_reduce",
                user_id=self.member.id,
                moderator_id=interaction.user.id,
                case_id=case["case_id"],
                detail=f"Reduced by {format_duration(seconds)}",
                dm_target=self.member,
                dm_title="Your Sentence Has Been Reduced",
                dm_fields=[
                    ("Case ID", f"#{case['case_id']}", True),
                    ("Reduced By", format_duration(seconds), True),
                    ("Time Remaining", format_duration(new_remaining), True),
                ],
                log_title="Sentence Reduced",
                log_fields=[
                    ("Member", f"{self.member.mention} ({self.member.id})", True),
                    ("Moderator", interaction.user.mention, True),
                    ("Case ID", f"#{case['case_id']}", True),
                    ("Reduced By", format_duration(seconds), True),
                    ("Time Remaining", format_duration(new_remaining), True),
                ],
            )
            return await interaction.followup.send(embed=build_embed(
                "Sentence Reduced",
                f"Case #{case['case_id']} reduced by {format_duration(seconds)}. New time remaining: {format_duration(new_remaining)}."
            ), ephemeral=True)

        if self.action == "settime":
            new_duration_seconds = seconds  # None means permanent
            if new_duration_seconds is None:
                await db().execute("UPDATE jail_cases SET duration_seconds = NULL WHERE guild_id = ? AND case_id = ? AND status = 'active'",
                                    (interaction.guild.id, case["case_id"]))
                await db().commit()
                await notify_and_log(
                    interaction.guild,
                    action="sentence_settime",
                    user_id=self.member.id,
                    moderator_id=interaction.user.id,
                    case_id=case["case_id"],
                    detail="Set to permanent",
                    dm_target=self.member,
                    dm_title="Your Sentence Timer Has Changed",
                    dm_fields=[
                        ("Case ID", f"#{case['case_id']}", True),
                        ("Time Remaining", "Permanent", True),
                    ],
                    log_title="Sentence Timer Updated",
                    log_fields=[
                        ("Member", f"{self.member.mention} ({self.member.id})", True),
                        ("Moderator", interaction.user.mention, True),
                        ("Case ID", f"#{case['case_id']}", True),
                        ("Time Remaining", "Permanent", True),
                    ],
                )
                return await interaction.followup.send(embed=build_embed(
                    "Sentence Updated", f"Case #{case['case_id']} is now permanent until manually released."), ephemeral=True)
            elapsed = now() - case["created_at"]
            new_duration = elapsed + new_duration_seconds
            await db().execute("UPDATE jail_cases SET duration_seconds = ? WHERE guild_id = ? AND case_id = ? AND status = 'active'",
                                (new_duration, interaction.guild.id, case["case_id"]))
            await db().commit()
            await notify_and_log(
                interaction.guild,
                action="sentence_settime",
                user_id=self.member.id,
                moderator_id=interaction.user.id,
                case_id=case["case_id"],
                detail=f"Time remaining set to {format_duration(new_duration_seconds)}",
                dm_target=self.member,
                dm_title="Your Sentence Timer Has Changed",
                dm_fields=[
                    ("Case ID", f"#{case['case_id']}", True),
                    ("Time Remaining", format_duration(new_duration_seconds), True),
                ],
                log_title="Sentence Timer Updated",
                log_fields=[
                    ("Member", f"{self.member.mention} ({self.member.id})", True),
                    ("Moderator", interaction.user.mention, True),
                    ("Case ID", f"#{case['case_id']}", True),
                    ("Time Remaining", format_duration(new_duration_seconds), True),
                ],
            )
            return await interaction.followup.send(embed=build_embed(
                "Sentence Updated",
                f"Case #{case['case_id']} time remaining set to {format_duration(new_duration_seconds)}."
            ), ephemeral=True)


class SentenceView(discord.ui.View):
    """Buttons shown on /sentence — each opens a modal to collect a duration."""

    def __init__(self, member: discord.Member, bot: commands.Bot):
        super().__init__(timeout=180)
        self.member = member
        self.bot = bot

    @discord.ui.button(label="Extend", style=discord.ButtonStyle.success)
    async def extend(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DurationModal("Extend Sentence", self.member, "extend", self.bot))

    @discord.ui.button(label="Reduce", style=discord.ButtonStyle.primary)
    async def reduce(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DurationModal("Reduce Sentence", self.member, "reduce", self.bot))

    @discord.ui.button(label="Set Time", style=discord.ButtonStyle.secondary)
    async def settime(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            DurationModal("Set Time Remaining", self.member, "settime", self.bot, allow_permanent=True))


class Sentence(commands.Cog):
    """
    Sentence management. A single /sentence command (not a group — see the
    naming note in jail_basic.py) posts an embed with a button for each
    action; each button opens a modal asking for a duration string.
    /sentence pardon and /sentence freeze/resume have been removed per
    spec; "permanent" is reachable through Set Time.

    /view sentence is a separate top-level group ("view") open to everyone
    (no trusted_only check) — it lets a jailed member look up their own
    case reason, time remaining, and case id without needing mod access.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    view = app_commands.Group(name="view", description="View your own info.")

    @app_commands.command(name="sentence", description="Manage an active jail sentence.")
    @app_commands.describe(member="The jailed member")
    @trusted_only()
    async def sentence(self, interaction: discord.Interaction, member: discord.Member):
        case = await _active_case(interaction.guild.id, member.id)
        if case is None:
            return await interaction.response.send_message(
                embed=error_embed(f"{member.mention} is not currently jailed."), ephemeral=True)
        remaining = None
        if case["duration_seconds"] is not None:
            remaining = max(0, case["duration_seconds"] - (now() - case["created_at"]))
        embed = build_embed(
            f"Sentence — {member.display_name}",
            None,
            fields=[
                ("Case ID", f"#{case['case_id']}", True),
                ("Time Remaining", format_duration(remaining), True),
            ],
        )
        await interaction.response.send_message(embed=embed, view=SentenceView(member, self.bot))

    @view.command(name="sentence", description="View your own current jail sentence: reason, duration, case id.")
    async def view_sentence(self, interaction: discord.Interaction):
        case = await _active_case(interaction.guild.id, interaction.user.id)
        if case is None:
            return await interaction.response.send_message(
                embed=error_embed("You are not currently jailed."), ephemeral=True)
        remaining = None
        if case["duration_seconds"] is not None:
            remaining = max(0, case["duration_seconds"] - (now() - case["created_at"]))
        embed = build_embed(
            "Your Sentence",
            None,
            fields=[
                ("Case ID", f"#{case['case_id']}", True),
                ("Time Remaining", format_duration(remaining), True),
                ("Reason", case["reason"] or "No reason provided", False),
            ],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Sentence(bot))
