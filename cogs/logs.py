import io
import discord
from discord import app_commands
from discord.ext import commands

from database import db
from utils.embeds import build_embed, error_embed
from utils.permissions import trusted_only


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    logs = app_commands.Group(name="logs", description="View and manage moderation logs.")

    @logs.command(name="jail", description="View jail logs.")
    @trusted_only()
    async def jail_logs(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM action_logs WHERE guild_id = ? ORDER BY created_at DESC LIMIT 15",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("Jail Logs", "No log entries yet."))
        lines = [f"<t:{r['created_at']}:f> — {r['action']} — <@{r['user_id']}>" +
                 (f" — {r['detail']}" if r["detail"] else "") for r in rows]
        await interaction.followup.send(embed=build_embed("Jail Logs", "\n".join(lines)))

    @logs.command(name="export", description="Export moderation logs.")
    @trusted_only()
    async def export(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM action_logs WHERE guild_id = ? ORDER BY created_at ASC", (interaction.guild.id,)
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=error_embed("There are no logs to export."))
        buffer = io.StringIO()
        buffer.write("timestamp,action,user_id,moderator_id,case_id,detail\n")
        for r in rows:
            detail = (r["detail"] or "").replace(",", ";").replace("\n", " ")
            buffer.write(f"{r['created_at']},{r['action']},{r['user_id']},{r['moderator_id']},{r['case_id']},{detail}\n")
        buffer.seek(0)
        file = discord.File(io.BytesIO(buffer.getvalue().encode()), filename=f"jail_logs_{interaction.guild.id}.csv")
        await interaction.followup.send(embed=build_embed("Log Export", "Full moderation log attached."), file=file)

    @logs.command(name="clear", description="Clear jail logs.")
    @app_commands.checks.has_permissions(administrator=True)
    async def clear(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await db().execute("DELETE FROM action_logs WHERE guild_id = ?", (interaction.guild.id,))
        await db().commit()
        await interaction.followup.send(embed=build_embed("Logs Cleared", "All jail logs have been cleared."))

    @logs.command(name="search", description="Search logs by user or case.")
    @app_commands.describe(member="Filter by member (optional)", case_id="Filter by case ID (optional)")
    @trusted_only()
    async def search(self, interaction: discord.Interaction,
                      member: discord.Member | None = None, case_id: int | None = None):
        await interaction.response.defer()
        if case_id is not None:
            cur = await db().execute("SELECT * FROM action_logs WHERE guild_id = ? AND case_id = ? ORDER BY created_at DESC",
                                      (interaction.guild.id, case_id))
        elif member is not None:
            cur = await db().execute(
                "SELECT * FROM action_logs WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 15",
                (interaction.guild.id, member.id))
        else:
            return await interaction.followup.send(embed=error_embed("Provide a member or a case ID to search."))
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("Log Search", "No matching log entries."))
        lines = [f"<t:{r['created_at']}:f> — {r['action']} — <@{r['user_id']}>" for r in rows]
        await interaction.followup.send(embed=build_embed("Log Search", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
