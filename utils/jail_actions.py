import discord

from database import db, now, get_guild_config, next_case_number
from utils.embeds import build_embed, format_duration
from utils.notify import notify_and_log

_expected_role_removals: set[tuple[int, int]] = set()


def expect_role_removal(guild_id: int, user_id: int) -> None:
    _expected_role_removals.add((guild_id, user_id))


def consume_expected_role_removal(guild_id: int, user_id: int) -> bool:
    """Returns True (and clears the flag) if this removal was expected."""
    key = (guild_id, user_id)
    if key in _expected_role_removals:
        _expected_role_removals.discard(key)
        return True
    return False


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


async def restore_or_create_cell_channel(
    guild: discord.Guild, cfg, jail_role: discord.Role | None, member: discord.Member, case,
) -> discord.TextChannel | None:
    """
    Used when re-establishing a jailed member's cell — e.g. after they
    rejoin the server. Reuses the case's existing cell channel if it's
    still there (just restores the member's view access to it, since
    Discord drops per-member overwrites when they leave), otherwise
    creates a fresh one numbered to match the case ID, same as /jail does.
    """
    existing = guild.get_channel(case["cell_channel_id"]) if case["cell_channel_id"] else None
    if existing is not None:
        try:
            await existing.set_permissions(
                member, view_channel=True, send_messages=True, read_message_history=True,
                reason="Restoring cell access after rejoin",
            )
        except discord.Forbidden:
            return existing
        return existing

    category = guild.get_channel(cfg["jail_category_id"]) if cfg["jail_category_id"] else None
    if category is None:
        return None
    new_channel = await _create_cell_channel(
        guild, category, jail_role, member, "Cell recreated after rejoin", case["case_id"]
    )
    if new_channel is not None:
        await db().execute(
            "UPDATE jail_cases SET cell_channel_id = ? WHERE guild_id = ? AND case_id = ? AND status = 'active'",
            (new_channel.id, guild.id, case["case_id"]),
        )
        await db().commit()
    return new_channel


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
    if cell_channel is not None:
        try:
            # Ping the member in their cell channel so they're notified they've been jailed.
            await cell_channel.send(
                content=member.mention,
                embed=build_embed(
                    "Cell Assignment Notice",
                    "You have been placed in this cell. Only you and staff can see this "
                    "channel; it will be deleted automatically once your sentence ends.",
                    fields=[
                        ("Reason", reason or "No reason provided", False),
                        ("Duration", format_duration(duration_seconds), True),
                        ("Case ID", f"#{case_id}", True),
                    ],
                ),
            )
        except discord.Forbidden:
            pass

    await notify_and_log(
        guild,
        action="jail",
        user_id=member.id,
        moderator_id=moderator.id,
        case_id=case_id,
        detail=reason,
        cfg=cfg,
        dm_target=member,
        dm_title="You Have Been Jailed",
        dm_description="You may submit an appeal at any time with `/appeal submit`.",
        dm_fields=[
            ("Server", guild.name, True),
            ("Case ID", f"#{case_id}", True),
            ("Duration", format_duration(duration_seconds), True),
            ("Cell", cell_channel.mention if cell_channel else "Not created", True),
            ("Reason", reason or "No reason provided", False),
        ],
        log_title="Member Jailed",
        log_fields=[
            ("Member", f"{member.mention} ({member.id})", True),
            ("Moderator", moderator.mention, True),
            ("Duration", format_duration(duration_seconds), True),
            ("Reason", reason or "No reason provided", False),
            ("Case ID", f"#{case_id}", True),
            ("Cell", cell_channel.mention if cell_channel else "Not created", True),
        ],
    )

    return True, f"{member.mention} has been jailed in {cell_channel.mention if cell_channel else 'the jail'}. Case #{case_id}.", case_id


async def release_member(
    guild: discord.Guild,
    member: discord.Member | None,
    moderator: discord.abc.User,
    case_id: int,
    method: str,
    bot: discord.Client,
    reason: str | None = None,
) -> tuple[bool, str]:
    """
    Releases a member from jail: restores their prior roles (if enabled),
    removes the jail role, closes the case. `method` is one of
    'released', 'pardoned', 'expired', 'forced'. `reason` is an optional
    note on why they were released (only used by moderator-initiated
    releases, e.g. /release).
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
                expect_role_removal(guild.id, member.id)
                try:
                    await member.remove_roles(jail_role, reason=f"Released ({method}) by {moderator}")
                except discord.Forbidden:
                    consume_expected_role_removal(guild.id, member.id)  # removal didn't happen; clear the flag
                    raise
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
    if reason:
        combined = f"{case['notes']}\nReleased: {reason}" if case["notes"] else f"Released: {reason}"
        await db().execute(
            "UPDATE jail_cases SET notes = ? WHERE guild_id = ? AND case_id = ? AND status = ?",
            (combined, guild.id, case_id, method),
        )
    await db().commit()

    # Tear down that member's private cell channel now that their case is closed.
    if case["cell_channel_id"]:
        cell_channel = guild.get_channel(case["cell_channel_id"])
        if cell_channel is not None:
            try:
                await cell_channel.delete(reason=f"Released ({method}) by {moderator}")
            except (discord.Forbidden, discord.NotFound):
                pass

    await notify_and_log(
        guild,
        action=method,
        user_id=case["user_id"],
        moderator_id=moderator.id if moderator else None,
        case_id=case_id,
        detail=reason,
        cfg=cfg,
        dm_target=member,
        dm_title="You Have Been Released",
        dm_fields=[
            ("Server", guild.name, True),
            ("Case ID", f"#{case_id}", True),
            ("Method", method.title(), True),
            ("Reason", reason or "No reason provided", False),
        ],
        log_title="Member Released",
        log_fields=[
            ("Member", member.mention if member else str(case["user_id"]), True),
            ("Moderator", moderator.mention if moderator else "System", True),
            ("Method", method.title(), True),
            ("Case ID", f"#{case_id}", True),
            ("Reason", reason or "No reason provided", False),
        ],
    )

    return True, f"Case #{case_id} closed ({method})."
