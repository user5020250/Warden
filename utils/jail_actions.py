"""
Core jailing / releasing logic, shared by every cog that needs to put
someone in jail or let them out (basic jail, autojail, solitary, probation,
appeal approval, etc). Keeping this in one place means every entry point
behaves the same real-world way: strip roles, apply the jail role, log a
case, notify the user, and post to the log channel.
"""

import discord

from database import db, now, get_guild_config, log_action, next_case_number
from utils.embeds import build_embed, format_duration


async def open_case(guild_id, case_id, user_id, moderator_id, reason, duration_seconds, role_backup_ids, cell_channel_id=None):
    await db().execute(
        """INSERT INTO jail_cases
           (case_id, guild_id, user_id, moderator_id, reason, created_at, duration_seconds,
            remaining_seconds, status, role_backup, cell_channel_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
        (
            case_id, guild_id, user_id, moderator_id, reason, now(), duration_seconds,
            duration_seconds, ",".join(str(r) for r in role_backup_ids), cell_channel_id,
        ),
    )
    await db().commit()
    return case_id


async def _create_cell_channel(
    guild: discord.Guild, category: discord.CategoryChannel, jail_role: discord.Role | None,
    member: discord.Member, reason: str, number: int,
) -> discord.TextChannel | None:
    """Creates a private cell channel numbered to match the case ID (so
    Case #3 lives in cell-3), visible only to the jailed member (and staff who
    can already see the category's private channels)."""
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    if jail_role is not None:
        # Deny the shared jail role explicitly so other jailed members can't see this cell.
        overwrites[jail_role] = discord.PermissionOverwrite(view_channel=False)
    try:
        channel = await category.create_text_channel(
            f"cell-{number}",
            overwrites=overwrites,
            reason=f"Jail cell for {member} ({reason})",
        )
    except discord.Forbidden:
        return None
    return channel


async def jail_member(
    guild: discord.Guild,
    member: discord.Member,
    moderator: discord.abc.User,
    reason: str,
    duration_seconds: int | None,
    bot: discord.Client,
) -> tuple[bool, str, int | None]:
    """
    Jails a member: swaps their roles for the jail role, opens a case,
    DMs them, and logs the action. Returns (success, message, case_id).
    """
    cfg = await get_guild_config(guild.id)
    if not cfg["jail_role_id"]:
        return False, "This server has not run /jailsetup yet.", None

    jail_role = guild.get_role(cfg["jail_role_id"])
    if jail_role is None:
        return False, "The configured jail role no longer exists. Run /jailsetup again.", None

    if jail_role in member.roles:
        return False, f"{member.mention} is already jailed.", None

    # Roles to strip (everyone but @everyone and the jail role itself),
    # kept so they can be restored on release.
    removable = [r for r in member.roles if r.name != "@everyone" and r.id != jail_role.id]
    role_backup_ids = [r.id for r in removable]

    try:
        if removable:
            await member.remove_roles(*removable, reason=f"Jailed by {moderator}: {reason}")
        await member.add_roles(jail_role, reason=f"Jailed by {moderator}: {reason}")
    except discord.Forbidden:
        return False, "I don't have permission to modify that member's roles.", None

    # The case ID and the cell channel number are the same value, and both
    # reuse the lowest number freed up by the last case that closed.
    case_number = await next_case_number(guild.id)

    cell_channel = None
    category = guild.get_channel(cfg["jail_category_id"]) if cfg["jail_category_id"] else None
    if category is not None:
        cell_channel = await _create_cell_channel(guild, category, jail_role, member, reason, case_number)

    case_id = await open_case(
        guild.id, case_number, member.id, moderator.id, reason, duration_seconds, role_backup_ids,
        cell_channel_id=cell_channel.id if cell_channel else None,
    )
    await log_action(guild.id, "jail", user_id=member.id, moderator_id=moderator.id,
                      case_id=case_id, detail=reason)

    if cell_channel is not None:
        try:
            await cell_channel.send(embed=build_embed(
                f"Welcome, **{member.display_name}**",
                f"**Reason:** {reason}\n**Duration:** {format_duration(duration_seconds)}\n**Case ID:** #{case_id}\n\n"
                "Only you and staff can see this channel. It will be deleted automatically once your sentence ends.",
            ))
        except discord.Forbidden:
            pass

    if cfg["dm_notifications"]:
        try:
            cell_line = f"\nCell: {cell_channel.mention}" if cell_channel else ""
            embed = build_embed(
                "**You have been jailed.**",
                f"**Server:** {guild.name}\n**Reason:** {reason}\n**Duration:** {format_duration(duration_seconds)}\n"
                f"**Case ID:** `#{case_id}{cell_line}`\n\nYou may submit an appeal with `/appeal` submit.",
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            pass

    if cfg["log_channel_id"]:
        log_channel = guild.get_channel(cfg["log_channel_id"])
        if log_channel:
            embed = build_embed(
                "Member Jailed",
                None,
                fields=[
                    ("Member", f"{member.mention} ({member.id})", True),
                    ("Moderator", moderator.mention, True),
                    ("Duration", format_duration(duration_seconds), True),
                    ("Reason", reason or "No reason provided", False),
                    ("Case ID", f"#{case_id}", True),
                    ("Cell", cell_channel.mention if cell_channel else "Not created", True),
                ],
            )
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                pass

    return True, f"{member.mention} has been jailed in {cell_channel.mention if cell_channel else 'the jail'}. Case #{case_id}.", case_id


async def release_member(
    guild: discord.Guild,
    member: discord.Member | None,
    moderator: discord.abc.User,
    case_id: int,
    method: str,
    bot: discord.Client,
) -> tuple[bool, str]:
    """
    Releases a member from jail: restores their prior roles (if enabled),
    removes the jail role, closes the case. `method` is one of
    'released', 'pardoned', 'expired', 'forced'.
    """
    cur = await db().execute(
        "SELECT * FROM jail_cases WHERE guild_id = ? AND case_id = ? AND status = 'active'",
        (guild.id, case_id),
    )
    case = await cur.fetchone()
    if case is None:
        return False, f"Case #{case_id} is not active."

    cfg = await get_guild_config(guild.id)
    jail_role = guild.get_role(cfg["jail_role_id"]) if cfg["jail_role_id"] else None

    if member is not None:
        try:
            if jail_role and jail_role in member.roles:
                await member.remove_roles(jail_role, reason=f"Released ({method}) by {moderator}")
            if cfg["auto_restore"] and case["role_backup"]:
                ids = [int(x) for x in case["role_backup"].split(",") if x]
                roles = [guild.get_role(i) for i in ids]
                roles = [r for r in roles if r is not None]
                if roles:
                    await member.add_roles(*roles, reason="Automatic role restoration on release")
        except discord.Forbidden:
            return False, "I don't have permission to modify that member's roles."

    await db().execute(
        "UPDATE jail_cases SET status = ?, released_at = ?, released_by = ? WHERE guild_id = ? AND case_id = ? AND status = 'active'",
        (method, now(), moderator.id if moderator else None, guild.id, case_id),
    )
    await db().commit()
    await log_action(guild.id, method, user_id=case["user_id"],
                      moderator_id=moderator.id if moderator else None, case_id=case_id)

    # Tear down that member's private cell channel now that their case is closed.
    if case["cell_channel_id"]:
        cell_channel = guild.get_channel(case["cell_channel_id"])
        if cell_channel is not None:
            try:
                await cell_channel.delete(reason=f"Released ({method}) by {moderator}")
            except (discord.Forbidden, discord.NotFound):
                pass

    if member is not None and cfg["dm_notifications"]:
        try:
            embed = build_embed(
                "You have been released",
                f"Server: {guild.name}\nCase ID: #{case_id}\nMethod: {method}",
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            pass

    if cfg["log_channel_id"]:
        log_channel = guild.get_channel(cfg["log_channel_id"])
        if log_channel:
            embed = build_embed(
                "Member Released",
                None,
                fields=[
                    ("Member", member.mention if member else str(case["user_id"]), True),
                    ("Moderator", moderator.mention if moderator else "System", True),
                    ("Method", method, True),
                    ("Case ID", f"#{case_id}", True),
                ],
            )
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                pass

    return True, f"Case #{case_id} closed ({method})."
