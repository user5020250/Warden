import discord
from discord import app_commands
from discord.ext import commands

from database import db, now
from utils.embeds import build_embed, error_embed, format_duration
from utils.permissions import trusted_only

PAGE_SIZE = 5


async def _build_history_rows(guild_id: int):
    """
    One row per member who has ever had a case in this guild: total case
    count, most recent reason, total time served, and whether they're
    currently active. Ordered by case count (most jailed first) to match
    "top jailed member cases".
    """
    cur = await db().execute("SELECT DISTINCT user_id FROM jail_cases WHERE guild_id = ?", (guild_id,))
    user_ids = [r["user_id"] for r in await cur.fetchall()]

    rows = []
    for user_id in user_ids:
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (guild_id, user_id),
        )
        cases = await cur.fetchall()
        total_served = 0
        active_case = None
        for c in cases:
            if c["status"] == "active":
                active_case = c
                if c["duration_seconds"] is not None:
                    total_served += min(now() - c["created_at"], c["duration_seconds"])
                else:
                    total_served += now() - c["created_at"]
            elif c["released_at"]:
                total_served += max(0, c["released_at"] - c["created_at"])
        rows.append({
            "user_id": user_id,
            "case_count": len(cases),
            "reason": cases[0]["reason"] or "No reason",
            "served": total_served,
            "active_case_id": active_case["case_id"] if active_case else None,
        })
    rows.sort(key=lambda r: r["case_count"], reverse=True)
    return rows


class JailHistoryPager(discord.ui.View):
    def __init__(self, rows: list[dict]):
        super().__init__(timeout=180)
        self.rows = rows
        self.page = 0
        self.max_page = max(0, (len(rows) - 1) // PAGE_SIZE)
        self._update_buttons()

    def _update_buttons(self):
        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= self.max_page

    def render(self) -> discord.Embed:
        start = self.page * PAGE_SIZE
        chunk = self.rows[start:start + PAGE_SIZE]
        if not chunk:
            return build_embed("Jail History", "No jail records yet.")
        lines = []
        for r in chunk:
            active = f"Active (Case #{r['active_case_id']})" if r["active_case_id"] else "Not currently jailed"
            lines.append(
                f"<@{r['user_id']}> — {r['case_count']} case(s) — Time served: {format_duration(r['served'])} "
                f"— Last reason: {r['reason']} — {active}"
            )
        return build_embed(f"Jail History (Page {self.page + 1}/{self.max_page + 1})", "\n".join(lines))

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.max_page, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()
        self.stop()


class ModUtils(commands.Cog):
    """
    Extra moderator tools for members already in jail. Grouped under
    /jailmod (not /jail) for the same naming-conflict reason as
    /jailinfo — Discord does not allow "jail" to be both a standalone
    command and a subcommand group. /jailmod mute has been removed
    per spec, and no other voice-related commands are included.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    jailmod = app_commands.Group(name="jailmod", description="Moderator tools for jailed members.")

    @jailmod.command(name="transfer", description="Transfer a jailed member to a different cell channel.")
    @app_commands.describe(member="The jailed member", channel="The cell channel to transfer them to")
    @trusted_only()
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, channel: discord.TextChannel):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))

        old_channel = interaction.guild.get_channel(row["cell_channel_id"]) if row["cell_channel_id"] else None

        try:
            await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True,
                                           reason=f"Transferred by {interaction.user}")
            if old_channel is not None:
                await old_channel.set_permissions(member, overwrite=None, reason=f"Transferred by {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("I don't have permission to modify that channel."))

        await db().execute(
            "UPDATE jail_cases SET cell_channel_id = ?, notes = COALESCE(notes || char(10), '') || ? "
            "WHERE guild_id = ? AND case_id = ? AND status = 'active'",
            (channel.id, f"Transferred to {channel.name} by {interaction.user}", interaction.guild.id, row["case_id"]),
        )
        await db().commit()
        await interaction.followup.send(embed=build_embed(
            "Case Transferred", f"Case #{row['case_id']} ({member.mention}) has been transferred to {channel.mention}."))

    @jailmod.command(name="notify", description="Resend jail notification.")
    @app_commands.describe(member="The jailed member")
    @trusted_only()
    async def notify(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, member.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=error_embed(f"{member.mention} is not currently jailed."))
        try:
            await member.send(embed=build_embed(
                "Jail Notification",
                f"Reminder: you are jailed in {interaction.guild.name}. Case #{row['case_id']}. Reason: {row['reason']}"
            ))
        except discord.Forbidden:
            return await interaction.followup.send(embed=error_embed("Could not DM that member; their DMs may be closed."))
        await interaction.followup.send(embed=build_embed("Notification Sent", f"Resent jail notification to {member.mention}."))

    @jailmod.command(name="history", description="Browse jail history for every member who has ever been jailed.")
    @trusted_only()
    async def history(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = await _build_history_rows(interaction.guild.id)
        view = JailHistoryPager(rows)
        await interaction.followup.send(embed=view.render(), view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModUtils(bot))
