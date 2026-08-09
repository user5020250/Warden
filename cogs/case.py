import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_case
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import staff_only
from utils.pagination import Paginator

# Naming note: the spec has both a direct "/case <case_id>" lookup and a
# "/case view / notes add / evidence add" subcommand group. Discord does
# not allow a slash command to be both a standalone command and a group of
# subcommands at the same time, so the direct lookup is exposed here as
# "/caseinfo <case_id>" instead, and "/case" stays a pure group.


class Case(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    case = app_commands.Group(name="case", description="View your cases or add moderator notes/evidence.")
    notes = app_commands.Group(name="notes", description="Manage moderator notes on a case.", parent=case)
    evidence = app_commands.Group(name="evidence", description="Manage evidence attached to a case.", parent=case)

    @app_commands.command(name="caseinfo", description="Displays complete information about a specific jail case.")
    @app_commands.describe(case_id="The case number to look up")
    @staff_only()
    async def caseinfo(self, interaction: discord.Interaction, case_id: int):
        await interaction.response.defer()
        case_row = await get_case(interaction.guild.id, case_id)
        if case_row is None:
            return await interaction.followup.send(embed=error_embed(f"Case `#{case_id}` could not be found."))

        cur = await db().execute(
            "SELECT * FROM case_notes WHERE guild_id = ? AND case_id = ? ORDER BY created_at ASC",
            (interaction.guild.id, case_id),
        )
        notes = await cur.fetchall()
        cur = await db().execute(
            "SELECT * FROM case_evidence WHERE guild_id = ? AND case_id = ? ORDER BY created_at ASC",
            (interaction.guild.id, case_id),
        )
        evidence = await cur.fetchall()

        notes_text = "\n".join(f"<@{n['moderator_id']}>: {n['note']}" for n in notes) or "None"
        evidence_text = "\n".join(f"[{e['filename'] or 'Attachment'}]({e['url']})" for e in evidence) or "None"
        status_text = {"active": "Active", "released": "Released", "expired": "Expired"}.get(case_row["status"], case_row["status"])

        embed = build_embed(
            f"Case `#{case_id}`",
            None,
            fields=[
                ("Member", f"<@{case_row['user_id']}>", True),
                ("Moderator", f"<@{case_row['moderator_id']}>", True),
                ("Status", f"`{status_text}`", True),
                ("Duration", f"`{format_duration(case_row['duration_seconds'])}`", True),
                ("Opened", f"<t:{case_row['created_at']}:F>", True),
                ("Reason", case_row["reason"] or "No reason provided", False),
                ("Notes", notes_text, False),
                ("Evidence", evidence_text, False),
            ],
        )
        await interaction.followup.send(embed=embed)

    @case.command(name="view", description="Shows your jail cases.")
    async def view(self, interaction: discord.Interaction):
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (interaction.guild.id, interaction.user.id),
        )
        rows = await cur.fetchall()
        lines = [
            f"`#{r['case_id']}` — Status: `{r['status']}` — {r['reason'] or 'No reason provided'}"
            for r in rows
        ]
        view = Paginator("Your Cases", lines, "You have no jail cases on record.")
        await interaction.response.send_message(embed=view.render(), view=view, ephemeral=True)

    @notes.command(name="add", description="Adds an internal moderator note to a case.")
    @app_commands.describe(case_id="The case number", note="The note to add")
    @staff_only()
    async def notes_add(self, interaction: discord.Interaction, case_id: int, note: str):
        case_row = await get_case(interaction.guild.id, case_id)
        if case_row is None:
            return await interaction.response.send_message(embed=error_embed(f"Case `#{case_id}` could not be found."))
        await db().execute(
            "INSERT INTO case_notes (guild_id, case_id, moderator_id, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (interaction.guild.id, case_id, interaction.user.id, note, now()),
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Note Added", f"Added a note to case `#{case_id}`."))

    @evidence.command(name="add", description="Adds attachment evidence to a case.")
    @app_commands.describe(case_id="The case number", attachment="The file to attach as evidence")
    @staff_only()
    async def evidence_add(self, interaction: discord.Interaction, case_id: int, attachment: discord.Attachment):
        case_row = await get_case(interaction.guild.id, case_id)
        if case_row is None:
            return await interaction.response.send_message(embed=error_embed(f"Case `#{case_id}` could not be found."))
        await db().execute(
            "INSERT INTO case_evidence (guild_id, case_id, moderator_id, url, filename, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (interaction.guild.id, case_id, interaction.user.id, attachment.url, attachment.filename, now()),
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Evidence Added", f"Added `{attachment.filename}` as evidence to case `#{case_id}`."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Case(bot))
