"""
Permission helpers shared across cogs.

Two tiers of "can moderate the jail system" access:
1. Anyone with the Moderate Members / Manage Roles permission (real Discord
   permission), OR the guild owner.
2. Anyone explicitly added via /jail trusted add, even without the Discord
   permission (e.g. a dedicated "Jail Team" that isn't full staff).

Exemptions (/jail exempt add) stop a role or user from ever being jailed,
including by autojail.
"""

import discord
from database import db


async def is_trusted(member: discord.Member) -> bool:
    if member.guild.owner_id == member.id:
        return True
    perms = member.guild_permissions
    if perms.manage_roles or perms.moderate_members or perms.administrator:
        return True
    cur = await db().execute(
        "SELECT 1 FROM trusted_moderators WHERE guild_id = ? AND user_id = ?",
        (member.guild.id, member.id),
    )
    row = await cur.fetchone()
    return row is not None


async def is_exempt(member: discord.Member) -> bool:
    role_ids = [r.id for r in member.roles]
    placeholders = ",".join("?" * len(role_ids)) if role_ids else "NULL"
    cur = await db().execute(
        f"""SELECT 1 FROM exempt_entries
            WHERE guild_id = ? AND (
                (entity_type = 'user' AND entity_id = ?)
                OR (entity_type = 'role' AND entity_id IN ({placeholders}))
            )""",
        (member.guild.id, member.id, *role_ids),
    )
    row = await cur.fetchone()
    return row is not None


def trusted_only():
    """App command check: requires trusted-moderator status."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        ok = await is_trusted(interaction.user)
        if not ok:
            raise PermissionDeniedError()
        return True

    return discord.app_commands.check(predicate)


class PermissionDeniedError(discord.app_commands.CheckFailure):
    pass
