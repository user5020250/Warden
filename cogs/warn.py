import discord
from discord import app_commands
from discord.ext import commands

from database import db, now
from utils.embeds import build_embed, error_embed
from utils.permissions import staff_only
from utils.notify import notify_and_log
from utils.pagination import Paginator

# Naming note: the spec has "/warnings <member>" (list) and
# "/warnings clear <member>" (a group) sharing the name "warnings", and
# "/warning <warning_id>" (lookup) and "/warning delete <warning_id>"
# sharing the name "warning" — both pairs hit the same standalone-command-
# vs-subcommand-group conflict as elsewhere in this bot. Everything is
# consolidated under one "/warnings" group: list, info, delete, clear.


class Warn(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    warnings = app_commands.Group(name="warnings", description="View and manage member warnings.")

    @app_commands.command(name="warn", description="Gives a member an official warning.")
    @app_commands.describe(member="The member to warn", reason="Why this member is being warned")
    @staff_only()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.defer()
        cur = await db().execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (interaction.guild.id, member.id, interaction.user.id, reason, now()),
        )
        await db().commit()
        warning_id = cur.lastrowid

        await notify_and_log(
            interaction.guild, action="warn", user_id=member.id, moderator_id=interaction.user.id, detail=reason,
            dm_target=member, dm_title="You Have Received a Warning",
            dm_fields=[
                ("Server", interaction.guild.name, True),
                ("Warning ID", f"`#{warning_id}`", True),
                ("Reason", reason, False),
            ],
            log_title="Member Warned",
            log_fields=[
                ("Member", f"{member.mention} (`{member.id}`)", True),
                ("Moderator", interaction.user.mention, True),
                ("Warning ID", f"`#{warning_id}`", True),
                ("Reason", reason, False),
            ],
        )
        await interaction.followup.send(embed=build_embed(
            "Warning Issued", f"{member.mention} has been warned. Warning ID: `#{warning_id}`."
        ))

    @warnings.command(name="list", description="Shows all warnings received by a member.")
    @app_commands.describe(member="The member to check")
    @staff_only()
    async def list_warnings(self, interaction: discord.Interaction, member: discord.Member):
        cur = await db().execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (interaction.guild.id, member.id),
        )
        rows = await cur.fetchall()
        lines = [f"`#{r['warning_id']}` — <t:{r['created_at']}:f> — {r['reason'] or 'No reason provided'}" for r in rows]
        view = Paginator(f"Warnings — {member}", lines, f"{member.mention} has no warnings on record.")
        await interaction.response.send_message(embed=view.render(), view=view)

    @warnings.command(name="info", description="Shows details about a specific warning.")
    @app_commands.describe(warning_id="The warning ID to look up")
    @staff_only()
    async def info(self, interaction: discord.Interaction, warning_id: int):
        cur = await db().execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND warning_id = ?", (interaction.guild.id, warning_id)
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.response.send_message(embed=error_embed(f"Warning `#{warning_id}` could not be found."))
        embed = build_embed(
            f"Warning `#{warning_id}`",
            None,
            fields=[
                ("Member", f"<@{row['user_id']}>", True),
                ("Moderator", f"<@{row['moderator_id']}>", True),
                ("Issued", f"<t:{row['created_at']}:F>", True),
                ("Reason", row["reason"] or "No reason provided", False),
            ],
        )
        await interaction.response.send_message(embed=embed)

    @warnings.command(name="delete", description="Deletes a warning.")
    @app_commands.describe(warning_id="The warning ID to delete")
    @staff_only()
    async def delete(self, interaction: discord.Interaction, warning_id: int):
        cur = await db().execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND warning_id = ?", (interaction.guild.id, warning_id)
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.response.send_message(embed=error_embed(f"Warning `#{warning_id}` could not be found."))
        await db().execute("DELETE FROM warnings WHERE guild_id = ? AND warning_id = ?", (interaction.guild.id, warning_id))
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Warning Deleted", f"Warning `#{warning_id}` has been deleted."))

    @warnings.command(name="clear", description="Clears a member's warning history.")
    @app_commands.describe(member="The member whose warnings should be cleared")
    @staff_only()
    async def clear(self, interaction: discord.Interaction, member: discord.Member):
        await db().execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Warnings Cleared", f"All warnings for {member.mention} have been cleared."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Warn(bot))
