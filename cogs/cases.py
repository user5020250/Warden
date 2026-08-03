import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_guild_config
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import trusted_only


class Cases(commands.Cog):
    """
    Case record management.

    Case numbers are reused (they double as the member's cell channel
    number), so a given case_id can match more than one historical row
    over time for the same guild. Every lookup here targets the single
    most recent row for that number. /case editduration has been removed
    per spec — timers are managed with /sentence instead.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    case = app_commands.Group(name="case", description="Manage jail case records.")

    async def _find(self, guild_id: int, case_id: int):
        cur = await db().execute(
            "SELECT rowid, * FROM jail_cases WHERE guild_id = ? AND case_id = ? ORDER BY created_at DESC LIMIT 1",
            (guild_id, case_id),
        )
        return await cur.fetchone()

    @case.command(name="view", description="View a case.")
    @app_commands.describe(case_id="The case ID to view")
    @trusted_only()
    async def view(self, interaction: discord.Interaction, case_id: int):
        await interaction.response.defer()
        row = await self._find(interaction.guild.id, case_id)
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"Case #{case_id} was not found."))
        remaining = None
        if row["status"] == "active" and row["duration_seconds"] is not None:
            remaining = max(0, row["duration_seconds"] - (now() - row["created_at"]))
        embed = build_embed(
            f"Case #{case_id}",
            None,
            fields=[
                ("Member", f"<@{row['user_id']}>", True),
                ("Moderator", f"<@{row['moderator_id']}>", True),
                ("Status", row["status"], True),
                ("Reason", row["reason"] or "None", False),
                ("Duration", format_duration(row["duration_seconds"]), True),
                ("Remaining", format_duration(remaining) if row["status"] == "active" else "N/A", True),
                ("Evidence", row["evidence"] or "None", False),
                ("Notes", row["notes"] or "None", False),
            ],
        )
        await interaction.followup.send(embed=embed)

    @case.command(name="editreason", description="Change the reason.")
    @app_commands.describe(case_id="The case ID", reason="The new reason")
    @trusted_only()
    async def editreason(self, interaction: discord.Interaction, case_id: int, reason: str):
        await interaction.response.defer()
        row = await self._find(interaction.guild.id, case_id)
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"Case #{case_id} was not found."))
        await db().execute("UPDATE jail_cases SET reason = ? WHERE rowid = ?", (reason, row["rowid"]))
        await db().commit()
        await interaction.followup.send(embed=build_embed("Case Updated", f"Case #{case_id} reason updated."))

    @case.command(name="delete", description="Delete a case.")
    @app_commands.describe(case_id="The case ID to delete")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete(self, interaction: discord.Interaction, case_id: int):
        await interaction.response.defer()
        row = await self._find(interaction.guild.id, case_id)
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"Case #{case_id} was not found."))
        await db().execute("DELETE FROM jail_cases WHERE rowid = ?", (row["rowid"],))
        await db().commit()
        await interaction.followup.send(embed=build_embed("Case Deleted", f"Case #{case_id} has been permanently deleted."))

    @case.command(name="evidence", description="Attach evidence.")
    @app_commands.describe(case_id="The case ID", evidence="Link or description of the evidence")
    @trusted_only()
    async def evidence(self, interaction: discord.Interaction, case_id: int, evidence: str):
        await interaction.response.defer()
        row = await self._find(interaction.guild.id, case_id)
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"Case #{case_id} was not found."))
        combined = f"{row['evidence']}\n{evidence}" if row["evidence"] else evidence
        await db().execute("UPDATE jail_cases SET evidence = ? WHERE rowid = ?", (combined, row["rowid"]))
        await db().commit()
        await interaction.followup.send(embed=build_embed("Evidence Attached", f"Evidence added to case #{case_id}."))

    @case.command(name="notes", description="Add private notes.")
    @app_commands.describe(case_id="The case ID", note="The note to add")
    @trusted_only()
    async def notes(self, interaction: discord.Interaction, case_id: int, note: str):
        await interaction.response.defer(ephemeral=True)
        row = await self._find(interaction.guild.id, case_id)
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"Case #{case_id} was not found."), ephemeral=True)
        combined = f"{row['notes']}\n{note}" if row["notes"] else note
        await db().execute("UPDATE jail_cases SET notes = ? WHERE rowid = ?", (combined, row["rowid"]))
        await db().commit()
        await interaction.followup.send(embed=build_embed("Note Added", f"Private note added to case #{case_id}."), ephemeral=True)

    @case.command(name="reopen", description="Reopen a closed case.")
    @app_commands.describe(case_id="The case ID to reopen")
    @trusted_only()
    async def reopen(self, interaction: discord.Interaction, case_id: int):
        await interaction.response.defer()
        row = await self._find(interaction.guild.id, case_id)
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"Case #{case_id} was not found."))
        if row["status"] == "active":
            return await interaction.followup.send(embed=error_embed("That case is already active."))

        guild = interaction.guild
        member = guild.get_member(row["user_id"])
        if member is None:
            return await interaction.followup.send(embed=error_embed(
                "That member is no longer in the server, so the case can't be reopened as an active jail."))

        # The number this case used might have been reused since it closed.
        existing = await db().execute(
            "SELECT 1 FROM jail_cases WHERE guild_id = ? AND case_id = ? AND status = 'active'",
            (guild.id, case_id),
        )
        if await existing.fetchone():
            return await interaction.followup.send(embed=error_embed(
                f"Case #{case_id} can't be reopened — that number is currently assigned to another active case."))

        cfg = await get_guild_config(guild.id)
        jail_role = guild.get_role(cfg["jail_role_id"]) if cfg["jail_role_id"] else None
        if jail_role is None:
            return await interaction.followup.send(embed=error_embed("Jail role is not configured. Run /jailsetup."))

        try:
            await member.add_roles(jail_role, reason=f"Case #{case_id} reopened by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to modify that member's roles."))

        await db().execute(
            "UPDATE jail_cases SET status = 'active', created_at = ?, released_at = NULL, released_by = NULL WHERE rowid = ?",
            (now(), row["rowid"]),
        )
        await db().commit()
        await interaction.followup.send(embed=build_embed("Case Reopened", f"Case #{case_id} has been reopened and {member.mention} is jailed again."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Cases(bot))
