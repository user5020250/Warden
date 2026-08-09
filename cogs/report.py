import discord
from discord import app_commands
from discord.ext import commands

from database import db, now
from utils.embeds import build_embed, error_embed
from utils.permissions import staff_only
from utils.notify import notify_and_log
from utils.pagination import Paginator


class Report(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="report", description="Reports a member to moderators for review.")
    @app_commands.describe(
        member="The member you are reporting",
        reason="Why you are reporting them",
        evidence="Optional attachment supporting the report",
    )
    async def report(self, interaction: discord.Interaction, member: discord.Member, reason: str, evidence: discord.Attachment = None):
        await interaction.response.defer(ephemeral=True)

        if member.id == interaction.user.id:
            return await interaction.followup.send(embed=error_embed("You cannot report yourself."), ephemeral=True)
        if member.bot:
            return await interaction.followup.send(embed=error_embed("You cannot report a bot."), ephemeral=True)

        cur = await db().execute(
            "INSERT INTO reports (guild_id, reporter_id, reported_id, reason, evidence_url, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (interaction.guild.id, interaction.user.id, member.id, reason, evidence.url if evidence else None, now()),
        )
        await db().commit()
        report_id = cur.lastrowid

        await notify_and_log(
            interaction.guild, action="report_submitted", user_id=member.id, moderator_id=interaction.user.id,
            detail=reason,
            log_title="New Report",
            log_fields=[
                ("Report ID", f"`#{report_id}`", True),
                ("Reporter", interaction.user.mention, True),
                ("Reported Member", member.mention, True),
                ("Reason", reason, False),
            ] + ([("Evidence", evidence.url, False)] if evidence else []),
        )

        await interaction.followup.send(embed=build_embed(
            "Report Submitted", f"Your report on {member.mention} has been submitted for review. Report ID: `#{report_id}`."
        ), ephemeral=True)

    @app_commands.command(name="reports", description="Displays pending and recent reports.")
    @staff_only()
    async def reports(self, interaction: discord.Interaction):
        cur = await db().execute(
            "SELECT * FROM reports WHERE guild_id = ? ORDER BY created_at DESC LIMIT 50", (interaction.guild.id,)
        )
        rows = await cur.fetchall()
        lines = [
            f"`#{r['report_id']}` — Status: `{r['status']}` — <@{r['reported_id']}> reported by <@{r['reporter_id']}>"
            for r in rows
        ]
        view = Paginator("Reports", lines, "There are no reports on record.")
        await interaction.response.send_message(embed=view.render(), view=view)

    @app_commands.command(name="reportinfo", description="Shows information about a specific report.")
    @app_commands.describe(report_id="The report ID to look up")
    @staff_only()
    async def reportinfo(self, interaction: discord.Interaction, report_id: int):
        cur = await db().execute(
            "SELECT * FROM reports WHERE guild_id = ? AND report_id = ?", (interaction.guild.id, report_id)
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.response.send_message(embed=error_embed(f"Report `#{report_id}` could not be found."))

        fields = [
            ("Reporter", f"<@{row['reporter_id']}>", True),
            ("Reported Member", f"<@{row['reported_id']}>", True),
            ("Status", f"`{row['status']}`", True),
            ("Submitted", f"<t:{row['created_at']}:F>", True),
            ("Reason", row["reason"], False),
        ]
        if row["evidence_url"]:
            fields.append(("Evidence", row["evidence_url"], False))
        if row["status"] == "closed":
            fields.append(("Closed By", f"<@{row['closed_by']}>", True))
            fields.append(("Close Reason", row["close_reason"] or "No reason provided", False))

        await interaction.response.send_message(embed=build_embed(f"Report `#{report_id}`", None, fields=fields))

    @app_commands.command(name="reportclose", description="Closes a report after it has been reviewed.")
    @app_commands.describe(report_id="The report ID to close", reason="Optional note on how it was resolved")
    @staff_only()
    async def reportclose(self, interaction: discord.Interaction, report_id: int, reason: str = None):
        cur = await db().execute(
            "SELECT * FROM reports WHERE guild_id = ? AND report_id = ?", (interaction.guild.id, report_id)
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.response.send_message(embed=error_embed(f"Report `#{report_id}` could not be found."))
        if row["status"] == "closed":
            return await interaction.response.send_message(embed=error_embed(f"Report `#{report_id}` is already closed."))

        await db().execute(
            "UPDATE reports SET status = 'closed', closed_by = ?, closed_at = ?, close_reason = ? WHERE report_id = ?",
            (interaction.user.id, now(), reason, report_id),
        )
        await db().commit()

        await notify_and_log(
            interaction.guild, action="report_closed", user_id=row["reported_id"], moderator_id=interaction.user.id,
            detail=reason,
            log_title="Report Closed",
            log_fields=[
                ("Report ID", f"`#{report_id}`", True),
                ("Closed By", interaction.user.mention, True),
                ("Reason", reason or "No reason provided", False),
            ],
        )
        await interaction.response.send_message(embed=build_embed("Report Closed", f"Report `#{report_id}` has been closed."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Report(bot))
