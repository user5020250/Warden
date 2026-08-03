import discord
from discord import app_commands
from discord.ext import commands

from database import db, now, get_guild_config
from utils.embeds import build_embed, error_embed
from utils.permissions import trusted_only, is_trusted
from utils.jail_actions import release_member


class AppealDecisionView(discord.ui.View):
    """
    Persistent view attached to every appeal embed posted in the appeal
    channel. Moderators click Approve or Decline instead of running a
    slash command, per spec.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="appeal_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, "approved")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="appeal_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, "denied")

    async def _decide(self, interaction: discord.Interaction, decision: str):
        if not isinstance(interaction.user, discord.Member) or not await is_trusted(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("You do not have permission to decide appeals."), ephemeral=True
            )

        await interaction.response.defer()

        cur = await db().execute(
            "SELECT * FROM appeals WHERE guild_id = ? AND message_id = ?",
            (interaction.guild.id, interaction.message.id),
        )
        appeal = await cur.fetchone()
        if appeal is None:
            return await interaction.followup.send(embed=error_embed("This appeal record could not be found."), ephemeral=True)
        if appeal["status"] != "pending":
            return await interaction.followup.send(
                embed=error_embed(f"This appeal has already been {appeal['status']}."), ephemeral=True
            )

        await db().execute(
            "UPDATE appeals SET status = ?, decided_by = ?, decided_at = ? WHERE appeal_id = ?",
            (decision, interaction.user.id, now(), appeal["appeal_id"]),
        )
        await db().commit()

        result_text = ""
        if decision == "approved":
            member = interaction.guild.get_member(appeal["user_id"])
            success, message = await release_member(
                interaction.guild, member, interaction.user, appeal["case_id"], "pardoned", interaction.client
            )
            result_text = message if success else f"Approved, but release failed: {message}"
        else:
            result_text = "The member remains jailed."

        embed = build_embed(
            f"Appeal {'Approved' if decision == 'approved' else 'Declined'}",
            None,
            fields=[
                ("Appellant", f"<@{appeal['user_id']}>", True),
                ("Case", f"#{appeal['case_id']}", True),
                ("Decided By", interaction.user.mention, True),
                ("Original Message", appeal["message"] or "None", False),
                ("Result", result_text, False),
            ],
        )
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(embed=embed, view=self)

        member = interaction.guild.get_member(appeal["user_id"])
        if member is not None:
            try:
                await member.send(embed=build_embed(
                    f"Your appeal was {decision}",
                    f"Case #{appeal['case_id']} in {interaction.guild.name}.\n{result_text}",
                ))
            except discord.Forbidden:
                pass


class Appeals(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Registered once so button clicks work even after a bot restart.
        self.bot.add_view(AppealDecisionView())

    appeal = app_commands.Group(name="appeal", description="Submit or manage jail appeals.")

    @appeal.command(name="submit", description="Submit an appeal.")
    @app_commands.describe(message="Why you believe you should be released")
    async def submit(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(ephemeral=True)
        cur = await db().execute(
            "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active'"
            " ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, interaction.user.id),
        )
        case = await cur.fetchone()
        if case is None:
            return await interaction.followup.send(embed=error_embed("You are not currently jailed."), ephemeral=True)

        cur2 = await db().execute(
            "SELECT 1 FROM appeals WHERE guild_id = ? AND case_id = ? AND status != 'denied'",
            (interaction.guild.id, case["case_id"]),
        )
        if await cur2.fetchone():
            return await interaction.followup.send(
                embed=error_embed("You've already submitted an appeal for this case. You may only submit again if it gets declined."),
                ephemeral=True,
            )

        cfg = await get_guild_config(interaction.guild.id)
        if not cfg["appeal_channel_id"]:
            return await interaction.followup.send(embed=error_embed("This server has not configured an appeal channel."), ephemeral=True)
        channel = interaction.guild.get_channel(cfg["appeal_channel_id"])
        if channel is None:
            return await interaction.followup.send(embed=error_embed("The configured appeal channel no longer exists."), ephemeral=True)

        embed = build_embed(
            "New Appeal",
            None,
            fields=[
                ("Appellant", interaction.user.mention, True),
                ("Case", f"#{case['case_id']}", True),
                ("Original Reason", case["reason"] or "None", False),
                ("Appeal Message", message, False),
            ],
        )
        sent = await channel.send(embed=embed, view=AppealDecisionView())

        cur3 = await db().execute(
            "INSERT INTO appeals (guild_id, case_id, user_id, message, created_at, channel_id, message_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (interaction.guild.id, case["case_id"], interaction.user.id, message, now(), channel.id, sent.id),
        )
        await db().commit()

        await interaction.followup.send(embed=build_embed(
            "Appeal Submitted", f"Your appeal for case #{case['case_id']} has been submitted for review."
        ), ephemeral=True)

    @appeal.command(name="view", description="View your appeal.")
    async def view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cur = await db().execute(
            "SELECT * FROM appeals WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, interaction.user.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=error_embed("You have not submitted any appeals."), ephemeral=True)
        embed = build_embed(
            "Your Latest Appeal",
            None,
            fields=[
                ("Case", f"#{row['case_id']}", True),
                ("Status", row["status"], True),
                ("Message", row["message"] or "None", False),
            ],
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @appeal.command(name="withdraw", description="Cancel your appeal.")
    async def withdraw(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cur = await db().execute(
            "SELECT * FROM appeals WHERE guild_id = ? AND user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
            (interaction.guild.id, interaction.user.id),
        )
        row = await cur.fetchone()
        if row is None:
            return await interaction.followup.send(embed=error_embed("You have no pending appeal to withdraw."), ephemeral=True)
        await db().execute("UPDATE appeals SET status = 'withdrawn', decided_at = ? WHERE appeal_id = ?",
                            (now(), row["appeal_id"]))
        await db().commit()

        channel = interaction.guild.get_channel(row["channel_id"]) if row["channel_id"] else None
        if channel:
            try:
                msg = await channel.fetch_message(row["message_id"])
                embed = build_embed("Appeal Withdrawn", f"Case #{row['case_id']} appeal was withdrawn by the appellant.")
                view = AppealDecisionView()
                for c in view.children:
                    c.disabled = True
                await msg.edit(embed=embed, view=view)
            except (discord.NotFound, discord.Forbidden):
                pass

        await interaction.followup.send(embed=build_embed("Appeal Withdrawn", "Your appeal has been withdrawn."), ephemeral=True)

    @appeal.command(name="list", description="List pending appeals.")
    @trusted_only()
    async def list_appeals(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute(
            "SELECT * FROM appeals WHERE guild_id = ? AND status = 'pending' ORDER BY created_at ASC",
            (interaction.guild.id,),
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.followup.send(embed=build_embed("Pending Appeals", "There are no pending appeals."))
        lines = [f"Case #{r['case_id']} — <@{r['user_id']}>" for r in rows]
        await interaction.followup.send(embed=build_embed("Pending Appeals", "\n".join(lines)))

async def setup(bot: commands.Bot):
    await bot.add_cog(Appeals(bot))
