import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_case
from utils.embeds import build_embed, error_embed
from utils.permissions import staff_only, is_staff
from utils.notify import notify_and_log
from utils.jail_actions import release_member
from utils.pagination import Paginator


class Appeal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    appeal = app_commands.Group(name="appeal", description="Submit or manage jail appeals.")

    @appeal.command(name="create", description="Allows a jailed member to appeal their case.")
    @app_commands.describe(case_id="Your case number", reason="Why you believe you should be released")
    async def create(self, interaction: discord.Interaction, case_id: int, reason: str):
        await interaction.response.defer(ephemeral=True)
        case_row = await get_case(interaction.guild.id, case_id)
        if case_row is None or case_row["user_id"] != interaction.user.id:
            return await interaction.followup.send(embed=error_embed(f"Case `#{case_id}` was not found under your account."), ephemeral=True)
        if case_row["status"] != "active":
            return await interaction.followup.send(embed=error_embed(f"Case `#{case_id}` is not currently active."), ephemeral=True)

        cur = await db().execute(
            "SELECT 1 FROM appeals WHERE guild_id = ? AND case_id = ? AND status = 'pending'",
            (interaction.guild.id, case_id),
        )
        if await cur.fetchone():
            return await interaction.followup.send(
                embed=error_embed(f"You already have a pending appeal for case `#{case_id}`."), ephemeral=True
            )

        cur = await db().execute(
            "INSERT INTO appeals (guild_id, case_id, user_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (interaction.guild.id, case_id, interaction.user.id, reason, now()),
        )
        await db().commit()
        appeal_id = cur.lastrowid

        await notify_and_log(
            interaction.guild, action="appeal_submitted", user_id=interaction.user.id, case_id=case_id, detail=reason,
            log_title="New Appeal",
            log_fields=[
                ("Appeal ID", f"`#{appeal_id}`", True),
                ("Appellant", interaction.user.mention, True),
                ("Case ID", f"`#{case_id}`", True),
                ("Reason", reason, False),
            ],
        )
        await interaction.followup.send(embed=build_embed(
            "Appeal Submitted", f"Your appeal for case `#{case_id}` has been submitted for review. Appeal ID: `#{appeal_id}`."
        ), ephemeral=True)

    @appeal.command(name="view", description="Shows an appeal and its details.")
    @app_commands.describe(appeal_id="The appeal ID to look up")
    async def view(self, interaction: discord.Interaction, appeal_id: int):
        cur = await db().execute(
            "SELECT * FROM appeals WHERE guild_id = ? AND appeal_id = ?", (interaction.guild.id, appeal_id)
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.response.send_message(embed=error_embed(f"Appeal `#{appeal_id}` could not be found."), ephemeral=True)
        if row["user_id"] != interaction.user.id and not (isinstance(interaction.user, discord.Member) and is_staff(interaction.user)):
            return await interaction.response.send_message(embed=error_embed("You do not have permission to view this appeal."), ephemeral=True)

        fields = [
            ("Appellant", f"<@{row['user_id']}>", True),
            ("Case ID", f"`#{row['case_id']}`", True),
            ("Status", f"`{row['status']}`", True),
            ("Submitted", f"<t:{row['created_at']}:F>", True),
            ("Reason", row["reason"], False),
        ]
        if row["status"] in ("approved", "denied"):
            fields.append(("Decided By", f"<@{row['decided_by']}>", True))
            fields.append(("Decision Reason", row["decision_reason"] or "No reason provided", False))
        await interaction.response.send_message(embed=build_embed(f"Appeal `#{appeal_id}`", None, fields=fields))

    @appeal.command(name="approve", description="Approves an appeal and releases the member.")
    @app_commands.describe(appeal_id="The appeal ID to approve")
    @staff_only()
    async def approve(self, interaction: discord.Interaction, appeal_id: int):
        await interaction.response.defer()
        appeal_row, error = await self._pending(interaction, appeal_id)
        if error:
            return await interaction.followup.send(embed=error_embed(error))

        member = interaction.guild.get_member(appeal_row["user_id"])
        success, message = await release_member(interaction.guild, member, interaction.user, appeal_row["case_id"], "released")
        result_text = message if success else f"Approved, but release failed: {message}"

        await db().execute(
            "UPDATE appeals SET status = 'approved', decided_by = ?, decided_at = ?, decision_reason = ? WHERE appeal_id = ?",
            (interaction.user.id, now(), result_text, appeal_id),
        )
        await db().commit()

        await notify_and_log(
            interaction.guild, action="appeal_approved", user_id=appeal_row["user_id"], moderator_id=interaction.user.id,
            case_id=appeal_row["case_id"], detail=result_text,
            dm_target=member, dm_title="Your Appeal Was Approved",
            dm_fields=[("Case ID", f"`#{appeal_row['case_id']}`", True), ("Server", interaction.guild.name, True)],
            log_title="Appeal Approved",
            log_fields=[
                ("Appellant", f"<@{appeal_row['user_id']}>", True),
                ("Case ID", f"`#{appeal_row['case_id']}`", True),
                ("Decided By", interaction.user.mention, True),
            ],
        )
        await interaction.followup.send(embed=build_embed("Appeal Approved", f"Appeal `#{appeal_id}` approved. {result_text}"))

    @appeal.command(name="deny", description="Denies an appeal.")
    @app_commands.describe(appeal_id="The appeal ID to deny", reason="Optional reason for denying")
    @staff_only()
    async def deny(self, interaction: discord.Interaction, appeal_id: int, reason: str = None):
        await interaction.response.defer()
        appeal_row, error = await self._pending(interaction, appeal_id)
        if error:
            return await interaction.followup.send(embed=error_embed(error))

        await db().execute(
            "UPDATE appeals SET status = 'denied', decided_by = ?, decided_at = ?, decision_reason = ? WHERE appeal_id = ?",
            (interaction.user.id, now(), reason, appeal_id),
        )
        await db().commit()

        member = interaction.guild.get_member(appeal_row["user_id"])
        await notify_and_log(
            interaction.guild, action="appeal_denied", user_id=appeal_row["user_id"], moderator_id=interaction.user.id,
            case_id=appeal_row["case_id"], detail=reason,
            dm_target=member, dm_title="Your Appeal Was Denied",
            dm_fields=[
                ("Case ID", f"`#{appeal_row['case_id']}`", True),
                ("Server", interaction.guild.name, True),
                ("Reason", reason or "No reason provided", False),
            ],
            log_title="Appeal Denied",
            log_fields=[
                ("Appellant", f"<@{appeal_row['user_id']}>", True),
                ("Case ID", f"`#{appeal_row['case_id']}`", True),
                ("Decided By", interaction.user.mention, True),
                ("Reason", reason or "No reason provided", False),
            ],
        )
        await interaction.followup.send(embed=build_embed("Appeal Denied", f"Appeal `#{appeal_id}` has been denied. The member remains jailed."))

    @appeal.command(name="cancel", description="Cancels your own pending appeal.")
    @app_commands.describe(appeal_id="The appeal ID to cancel")
    async def cancel(self, interaction: discord.Interaction, appeal_id: int):
        cur = await db().execute(
            "SELECT * FROM appeals WHERE guild_id = ? AND appeal_id = ?", (interaction.guild.id, appeal_id)
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.response.send_message(embed=error_embed(f"Appeal `#{appeal_id}` could not be found."), ephemeral=True)
        if row["user_id"] != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("You can only cancel your own appeal."), ephemeral=True)
        if row["status"] != "pending":
            return await interaction.response.send_message(embed=error_embed(f"Appeal `#{appeal_id}` is not pending."), ephemeral=True)

        await db().execute(
            "UPDATE appeals SET status = 'cancelled', decided_at = ? WHERE appeal_id = ?", (now(), appeal_id)
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Appeal Cancelled", f"Appeal `#{appeal_id}` has been cancelled."), ephemeral=True)

    @app_commands.command(name="appeals", description="Shows pending appeals.")
    @staff_only()
    async def appeals(self, interaction: discord.Interaction):
        cur = await db().execute(
            "SELECT * FROM appeals WHERE guild_id = ? AND status = 'pending' ORDER BY created_at ASC",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        lines = [f"`#{r['appeal_id']}` — Case `#{r['case_id']}` — <@{r['user_id']}>" for r in rows]
        view = Paginator("Pending Appeals", lines, "There are no pending appeals.")
        await interaction.response.send_message(embed=view.render(), view=view)

    async def _pending(self, interaction: discord.Interaction, appeal_id: int):
        cur = await db().execute(
            "SELECT * FROM appeals WHERE guild_id = ? AND appeal_id = ?", (interaction.guild.id, appeal_id)
        )
        row = await cur.fetchone()
        if row is None:
            return None, f"Appeal `#{appeal_id}` could not be found."
        if row["status"] != "pending":
            return None, f"Appeal `#{appeal_id}` has already been {row['status']}."
        return row, None


async def setup(bot: commands.Bot):
    await bot.add_cog(Appeal(bot))
