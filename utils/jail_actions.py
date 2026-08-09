"""
Shared logic for putting a member in jail and taking them back out of it.
Used by /jail, /unjail, /sentence end, and the scheduler's automatic
release when a sentence's duration runs out — so all four paths strip/
restore roles, manage the cell channel, and update the case row the same
way.
"""

import discord

from database import db, now, next_case_number, get_guild_config
from utils.embeds import build_embed


async def jail_member(
    guild: discord.Guild,
    member: discord.Member,
    moderator: discord.abc.User,
    reason: str | None,
    duration_seconds: int | None,
) -> tuple[bool, str, int | None]:
    """Strips the member's current roles, applies the jail role, opens a
    case, and creates a private cell channel. Returns (success, message,
    case_id)."""
    cfg = await get_guild_config(guild.id)
    if not cfg["jail_role_id"]:
        return False, "This server has not configured a jail role. Run /jailsetup or /jailconfig role first.", None
    jail_role = guild.get_role(cfg["jail_role_id"])
    if jail_role is None:
        return False, "The configured jail role no longer exists. Run /jailsetup or /jailconfig role again.", None
    if not cfg["jail_category_id"]:
        return False, "This server has not configured a jail category. Run /jailsetup first.", None
    category = guild.get_channel(cfg["jail_category_id"])
    if category is None:
        return False, "The configured jail category no longer exists. Run /jailsetup again.", None

    case_id = await next_case_number(guild.id)
    role_backup = ",".join(str(r.id) for r in member.roles if not r.is_default())

    try:
        roles_to_remove = [r for r in member.roles if not r.is_default()]
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason=f"Jailed by {moderator} (case #{case_id})")
        await member.add_roles(jail_role, reason=f"Jailed by {moderator} (case #{case_id})")
    except discord.Forbidden:
        return False, "I don't have permission to modify that member's roles.", None

    try:
        cell_channel = await category.create_text_channel(
            f"cell-{case_id}",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            },
            reason=f"Jail cell for case #{case_id}",
        )
    except discord.Forbidden:
        cell_channel = None

    await db().execute(
        "INSERT INTO jail_cases (case_id, guild_id, user_id, moderator_id, reason, created_at,"
        " duration_seconds, role_backup, cell_channel_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (case_id, guild.id, member.id, moderator.id, reason, now(), duration_seconds,
         role_backup, cell_channel.id if cell_channel else None),
    )
    await db().commit()

    return True, "Jailed successfully.", case_id


async def release_member(
    guild: discord.Guild,
    member: discord.Member | None,
    moderator: discord.abc.User,
    case_id: int,
    status: str,
) -> tuple[bool, str]:
    """Restores the member's prior roles, removes the jail role, deletes
    the cell channel, and closes the case row with the given status
    ('released' or 'expired'). Returns (success, message)."""
    cur = await db().execute(
        "SELECT * FROM jail_cases WHERE guild_id = ? AND case_id = ? AND status = 'active'",
        (guild.id, case_id),
    )
    case = await cur.fetchone()
    if case is None:
        return False, f"Case #{case_id} is not currently active."

    cfg = await get_guild_config(guild.id)
    jail_role = guild.get_role(cfg["jail_role_id"]) if cfg["jail_role_id"] else None

    if member is not None:
        try:
            if jail_role is not None:
                await member.remove_roles(jail_role, reason=f"Released by {moderator} (case #{case_id})")
            if case["role_backup"]:
                role_ids = [int(r) for r in case["role_backup"].split(",") if r]
                roles = [guild.get_role(r) for r in role_ids]
                roles = [r for r in roles if r is not None]
                if roles:
                    await member.add_roles(*roles, reason=f"Roles restored on release (case #{case_id})")
        except discord.Forbidden:
            pass

    if case["cell_channel_id"]:
        cell_channel = guild.get_channel(case["cell_channel_id"])
        if cell_channel is not None:
            try:
                await cell_channel.delete(reason=f"Case #{case_id} closed")
            except discord.Forbidden:
                pass

    await db().execute(
        "UPDATE jail_cases SET status = ?, released_at = ?, released_by = ?, cell_channel_id = NULL"
        " WHERE guild_id = ? AND case_id = ?",
        (status, now(), moderator.id if moderator else None, guild.id, case_id),
    )
    await db().commit()

    return True, "Released successfully."
