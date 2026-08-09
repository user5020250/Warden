"""
Server-event listeners that keep the jail system honest even when
someone bypasses the bot's own commands: leaving/rejoining to shed the
jail role, a moderator manually unassigning it in Discord's role UI, or
someone deleting the jail role/category/log/appeal channel directly
instead of through /jailconfig.

None of this replaces /jailsetup or /jailconfig — it just makes sure the
system self-heals (or at least alerts a human) when reality drifts from
what the database still thinks is true.
"""

import discord
from discord.ext import commands

from database import db, get_active_case, get_guild_config, log_action, clear_dead_cell_channel
from utils.embeds import build_embed
from utils.jail_actions import restore_or_create_cell_channel, consume_expected_role_removal


async def _alert(guild: discord.Guild, cfg, title: str, description: str) -> None:
    """Best-effort admin alert: post to the configured log channel if it
    still exists, otherwise fall back to DMing the guild owner so a
    config-drift problem doesn't go completely unnoticed."""
    channel = guild.get_channel(cfg["log_channel_id"]) if cfg and cfg["log_channel_id"] else None
    if channel is not None:
        try:
            await channel.send(embed=build_embed(title, description))
            return
        except discord.Forbidden:
            pass
    owner = guild.owner
    if owner is not None:
        try:
            await owner.send(embed=build_embed(f"[{guild.name}] {title}", description))
        except discord.Forbidden:
            pass


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # Rejoin re-jailing: Discord strips a member's roles on leave, so a
    # jailed member who leaves and rejoins would otherwise walk out free
    # while their case still shows active in the database.
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        case = await get_active_case(member.guild.id, member.id)
        if case is None:
            return

        cfg = await get_guild_config(member.guild.id)
        jail_role = member.guild.get_role(cfg["jail_role_id"]) if cfg["jail_role_id"] else None
        if jail_role is None:
            await _alert(
                member.guild, cfg, "Jailed Member Rejoined — Action Needed",
                f"{member.mention} has an active case (#{case['case_id']}) and just rejoined, but the "
                "configured jail role no longer exists, so it could not be reapplied. Run /jailsetup.",
            )
            return

        try:
            await member.add_roles(jail_role, reason=f"Rejoined while jail case #{case['case_id']} is active")
        except discord.Forbidden:
            await _alert(
                member.guild, cfg, "Jailed Member Rejoined — Action Needed",
                f"{member.mention} has an active case (#{case['case_id']}) and just rejoined, but I don't have "
                "permission to reapply the jail role.",
            )
            return

        cell_channel = await restore_or_create_cell_channel(member.guild, cfg, jail_role, member, case)

        await log_action(member.guild.id, "rejoin_rejailed", user_id=member.id, case_id=case["case_id"],
                          detail="Jail role reapplied after rejoin")

        if cfg["log_channel_id"]:
            log_channel = member.guild.get_channel(cfg["log_channel_id"])
            if log_channel is not None:
                try:
                    await log_channel.send(embed=build_embed(
                        "Jailed Member Rejoined",
                        None,
                        fields=[
                            ("Member", f"{member.mention} ({member.id})", True),
                            ("Case ID", f"#{case['case_id']}", True),
                            ("Cell", cell_channel.mention if cell_channel else "Could not restore", True),
                        ],
                    ))
                except discord.Forbidden:
                    pass

        if cfg["dm_notifications"]:
            try:
                await member.send(embed=build_embed(
                    "You Are Still Jailed",
                    "You left while jailed, so your sentence did not end. You have been placed back in "
                    "jail on rejoining.",
                    fields=[("Case ID", f"#{case['case_id']}", True)],
                ))
            except discord.Forbidden:
                pass

    # ------------------------------------------------------------------
    # Leaving while jailed: the case stays active (so rejoin re-jailing
    # above has something to act on) but this makes sure staff know it
    # happened, since the member's cell channel is now empty/inaccessible.
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        case = await get_active_case(member.guild.id, member.id)
        if case is None:
            return

        cfg = await get_guild_config(member.guild.id)
        await log_action(member.guild.id, "left_while_jailed", user_id=member.id, case_id=case["case_id"],
                          detail="Member left the server with an active jail case")

        if cfg["log_channel_id"]:
            log_channel = member.guild.get_channel(cfg["log_channel_id"])
            if log_channel is not None:
                try:
                    await log_channel.send(embed=build_embed(
                        "Jailed Member Left the Server",
                        "Their case remains active and they will be placed back in jail automatically if "
                        "they rejoin.",
                        fields=[
                            ("Member", f"{member} ({member.id})", True),
                            ("Case ID", f"#{case['case_id']}", True),
                        ],
                    ))
                except discord.Forbidden:
                    pass

    # ------------------------------------------------------------------
    # Manual role removal protection: if the jail role disappears from a
    # jailed member's roles by any path other than /release (someone
    # dragging it off in Discord's member panel, a role hierarchy change,
    # etc.), reapply it and flag what happened.
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        cfg = await get_guild_config(after.guild.id)
        jail_role_id = cfg["jail_role_id"]
        if not jail_role_id:
            return

        had_role = any(r.id == jail_role_id for r in before.roles)
        has_role = any(r.id == jail_role_id for r in after.roles)
        if not (had_role and not has_role):
            return

        if consume_expected_role_removal(after.guild.id, after.id):
            return  # this was /release removing the role itself, not a manual/unexpected removal

        case = await get_active_case(after.guild.id, after.id)
        if case is None:
            return  # role removal matches an intentional /release, nothing to correct

        jail_role = after.guild.get_role(jail_role_id)
        if jail_role is None:
            return

        try:
            await after.add_roles(jail_role, reason="Reapplied: jail role was removed outside of /release "
                                                      f"while case #{case['case_id']} is still active")
        except discord.Forbidden:
            await _alert(
                after.guild, cfg, "Jail Role Manually Removed — Action Needed",
                f"{after.mention}'s jail role was removed outside of /release while case #{case['case_id']} "
                "is still active, and I don't have permission to reapply it.",
            )
            return

        await log_action(after.guild.id, "jail_role_manually_removed", user_id=after.id, case_id=case["case_id"],
                          detail="Jail role was removed outside of /release and has been reapplied")

        if cfg["log_channel_id"]:
            log_channel = after.guild.get_channel(cfg["log_channel_id"])
            if log_channel is not None:
                try:
                    await log_channel.send(embed=build_embed(
                        "Jail Role Reapplied",
                        "The jail role was removed from a member with an active case outside of /release. "
                        "It has been reapplied automatically. If this member should actually be released, "
                        "use /release instead of removing the role directly.",
                        fields=[
                            ("Member", f"{after.mention} ({after.id})", True),
                            ("Case ID", f"#{case['case_id']}", True),
                        ],
                    ))
                except discord.Forbidden:
                    pass

    # ------------------------------------------------------------------
    # Config drift: the jail role or a jail-system channel gets deleted
    # directly in Discord instead of through the bot.
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        cfg = await get_guild_config(role.guild.id)
        if cfg["jail_role_id"] != role.id:
            return
        await log_action(role.guild.id, "jail_role_deleted", detail=f"Jail role '{role.name}' was deleted")
        await _alert(
            role.guild, cfg, "Jail Role Deleted — Action Needed",
            f"The configured jail role (`{role.name}`) was deleted. Jailed members can no longer be "
            "distinguished until you run /jailsetup again to create a new one.",
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        cfg = await get_guild_config(channel.guild.id)

        if cfg["jail_category_id"] == channel.id:
            await log_action(channel.guild.id, "jail_category_deleted", detail=f"Jail category '{channel.name}' was deleted")
            await _alert(
                channel.guild, cfg, "Jail Category Deleted — Action Needed",
                f"The jail category (`{channel.name}`) was deleted. New cell channels cannot be created "
                "until you run /jailsetup again.",
            )
            return

        if cfg["log_channel_id"] == channel.id:
            await log_action(channel.guild.id, "log_channel_deleted", detail=f"Log channel '{channel.name}' was deleted")
            await _alert(
                channel.guild, cfg, "Log Channel Deleted — Action Needed",
                f"The configured log channel (`{channel.name}`) was deleted. Set a new one with "
                "/jailconfig logchannel.",
            )
            return

        if cfg["appeal_channel_id"] == channel.id:
            await log_action(channel.guild.id, "appeal_channel_deleted", detail=f"Appeal channel '{channel.name}' was deleted")
            await _alert(
                channel.guild, cfg, "Appeal Channel Deleted — Action Needed",
                f"The configured appeal channel (`{channel.name}`) was deleted. Members can no longer "
                "submit appeals until you set a new one with /jailconfig appealchannel.",
            )
            return

        # A cell channel (or a visitation-granted channel) being deleted directly: clear the
        # dangling reference so future commands don't error out trying to reach a dead channel.
        cur = await db().execute(
            "SELECT case_id FROM jail_cases WHERE guild_id = ? AND cell_channel_id = ? AND status = 'active'",
            (channel.guild.id, channel.id),
        )
        row = await cur.fetchone()
        if row is not None:
            await clear_dead_cell_channel(channel.guild.id, channel.id)
            await log_action(channel.guild.id, "cell_channel_deleted", case_id=row["case_id"],
                              detail=f"Cell channel '{channel.name}' was deleted directly; case reference cleared")
            await _alert(
                channel.guild, cfg, "Cell Channel Deleted — Action Needed",
                f"Case #{row['case_id']}'s cell channel (`{channel.name}`) was deleted directly. The case "
                "is still active but no longer has a cell; a new one will be created if the member is "
                "transferred, or you can release and re-jail them.",
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
