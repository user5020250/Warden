"""
Permission model for Warden.

"Staff" means anyone with the Moderate Members, Manage Roles, or
Administrator Discord permission, or the guild owner. There is no separate
trusted-user list — access is tied directly to real Discord permissions, so
server owners manage who can moderate through their existing role setup.
"""

import discord


def is_staff(member: discord.Member) -> bool:
    if member.guild.owner_id == member.id:
        return True
    perms = member.guild_permissions
    return perms.administrator or perms.manage_roles or perms.moderate_members


def staff_only():
    """App command check: requires staff-level Discord permissions."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        if not is_staff(interaction.user):
            raise PermissionDeniedError()
        return True

    return discord.app_commands.check(predicate)


class PermissionDeniedError(discord.app_commands.CheckFailure):
    pass
