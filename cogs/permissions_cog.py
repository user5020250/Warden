import discord
from discord import app_commands
from discord.ext import commands

from database import db
from utils.embeds import build_embed, error_embed


# ----------------------------------------------------------------------
# /jailmanage exempt - Add/Remove buttons, each opens a user search select
# ----------------------------------------------------------------------
class ExemptAddSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Search for a user to exempt", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        await db().execute(
            "INSERT OR IGNORE INTO exempt_entries (guild_id, entity_id, entity_type) VALUES (?, ?, 'user')",
            (interaction.guild.id, target.id),
        )
        await db().commit()
        await interaction.response.send_message(
            embed=build_embed("Exemption Added", f"{target.mention} can no longer be jailed."), ephemeral=True)


class ExemptRemoveSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Search for a user to remove exemption from", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        result = await db().execute(
            "DELETE FROM exempt_entries WHERE guild_id = ? AND entity_id = ? AND entity_type = 'user'",
            (interaction.guild.id, target.id),
        )
        await db().commit()
        if result.rowcount == 0:
            return await interaction.response.send_message(
                embed=error_embed(f"{target.mention} was not exempt."), ephemeral=True)
        await interaction.response.send_message(
            embed=build_embed("Exemption Removed", f"{target.mention} can be jailed again."), ephemeral=True)


class ExemptAddRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Search for a role to exempt", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        await db().execute(
            "INSERT OR IGNORE INTO exempt_entries (guild_id, entity_id, entity_type) VALUES (?, ?, 'role')",
            (interaction.guild.id, target.id),
        )
        await db().commit()
        await interaction.response.send_message(
            embed=build_embed("Exemption Added", f"{target.mention} can no longer be jailed."), ephemeral=True)


class ExemptRemoveRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Search for a role to remove exemption from", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        result = await db().execute(
            "DELETE FROM exempt_entries WHERE guild_id = ? AND entity_id = ? AND entity_type = 'role'",
            (interaction.guild.id, target.id),
        )
        await db().commit()
        if result.rowcount == 0:
            return await interaction.response.send_message(
                embed=error_embed(f"{target.mention} was not exempt."), ephemeral=True)
        await interaction.response.send_message(
            embed=build_embed("Exemption Removed", f"{target.mention} can be jailed again."), ephemeral=True)


class ExemptAddUserView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ExemptAddSelect())


class ExemptAddRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ExemptAddRoleSelect())


class ExemptRemoveUserView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ExemptRemoveSelect())


class ExemptRemoveRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ExemptRemoveRoleSelect())


class ExemptManageView(discord.ui.View):
    """
    Posted by /jailmanage exempt. Exemptions can target a role or a user,
    so Add/Remove each offer a User button and a Role button; the chosen
    one opens the matching search select (UserSelect or RoleSelect).
    """

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Add User", style=discord.ButtonStyle.success, row=0)
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_embed("Add Exemption", "Search for the user to exempt from ever being jailed."),
            view=ExemptAddUserView(), ephemeral=True)

    @discord.ui.button(label="Add Role", style=discord.ButtonStyle.success, row=0)
    async def add_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_embed("Add Exemption", "Search for the role to exempt from ever being jailed."),
            view=ExemptAddRoleView(), ephemeral=True)

    @discord.ui.button(label="Remove User", style=discord.ButtonStyle.danger, row=1)
    async def remove_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_embed("Remove Exemption", "Search for the user to remove the exemption from."),
            view=ExemptRemoveUserView(), ephemeral=True)

    @discord.ui.button(label="Remove Role", style=discord.ButtonStyle.danger, row=1)
    async def remove_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_embed("Remove Exemption", "Search for the role to remove the exemption from."),
            view=ExemptRemoveRoleView(), ephemeral=True)


# ----------------------------------------------------------------------
# /jailmanage trusted - Add/Remove buttons, each opens a user search select
# ----------------------------------------------------------------------
class TrustedAddSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Search for a user to grant jail command access", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        await db().execute(
            "INSERT OR IGNORE INTO trusted_moderators (guild_id, user_id) VALUES (?, ?)",
            (interaction.guild.id, target.id),
        )
        await db().commit()
        await interaction.response.send_message(
            embed=build_embed("Trusted Moderator Added", f"{target.mention} can now use jail commands."),
            ephemeral=True)


class TrustedRemoveSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Search for a user to revoke jail command access", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        result = await db().execute(
            "DELETE FROM trusted_moderators WHERE guild_id = ? AND user_id = ?",
            (interaction.guild.id, target.id),
        )
        await db().commit()
        if result.rowcount == 0:
            return await interaction.response.send_message(
                embed=error_embed(f"{target.mention} was not a trusted moderator."), ephemeral=True)
        await interaction.response.send_message(
            embed=build_embed("Trusted Moderator Removed", f"{target.mention} no longer has jail command access."),
            ephemeral=True)


class TrustedAddView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(TrustedAddSelect())


class TrustedRemoveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(TrustedRemoveSelect())


class TrustedManageView(discord.ui.View):
    """Posted by /jailmanage trusted — Add / Remove buttons, each opens a user-search select."""

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Add", style=discord.ButtonStyle.success)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_embed("Add Trusted Moderator", "Search for the member to grant jail command access to."),
            view=TrustedAddView(), ephemeral=True)

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_embed("Remove Trusted Moderator", "Search for the member to revoke jail command access from."),
            view=TrustedRemoveView(), ephemeral=True)


# ----------------------------------------------------------------------
# /jailperms - dropdown: Trusted Moderators / Exempt Roles & Users
# ----------------------------------------------------------------------
class JailPermsSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Trusted Moderators", value="trusted",
                                  description="Members granted jail command access."),
            discord.SelectOption(label="Exempt Roles & Users", value="exempt",
                                  description="Roles/users who can never be jailed."),
        ]
        super().__init__(placeholder="Choose what to view", options=options, custom_id="jailperms_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.values[0] == "trusted":
            cur = await db().execute("SELECT user_id FROM trusted_moderators WHERE guild_id = ?", (interaction.guild.id,))
            rows = await cur.fetchall()
            text = "\n".join(f"<@{r['user_id']}>" for r in rows) or "None"
            embed = build_embed("Trusted Moderators", text, fields=[
                ("Note", "Members with Manage Roles, Moderate Members, Administrator, or who own the server "
                         "can always use jail commands even if not listed above.", False),
            ])
        else:
            cur = await db().execute("SELECT entity_id, entity_type FROM exempt_entries WHERE guild_id = ?", (interaction.guild.id,))
            rows = await cur.fetchall()
            text = "\n".join(
                f"<@&{r['entity_id']}>" if r["entity_type"] == "role" else f"<@{r['entity_id']}>" for r in rows
            ) or "None"
            embed = build_embed("Exempt Roles & Users", text)
        await interaction.followup.send(embed=embed, ephemeral=True)


class JailPermsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(JailPermsSelect())


class PermissionsCog(commands.Cog):
    """
    Exemptions and trusted-moderator management.

    /jailperms shows a dropdown to browse trusted moderators or exemptions.
    /jailmanage exempt posts Add User/Add Role/Remove User/Remove Role
    buttons (exemptions can target a role or a user), each opening the
    matching search select (UserSelect or RoleSelect). /jailmanage trusted
    stays user-only, since trusted-moderator access is tied to individual
    members, not roles.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    jailmanage = app_commands.Group(name="jailmanage", description="Manage jail system permissions.",
                                     default_permissions=discord.Permissions(administrator=True))

    @jailmanage.command(name="exempt", description="Exempt or un-exempt a role or user from ever being jailed.")
    async def jailmanage_exempt(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=build_embed("Manage Exemptions", "Add or remove a user's exemption from jailing."),
            view=ExemptManageView())

    @jailmanage.command(name="trusted", description="Grant or revoke jail command access for a member.")
    async def jailmanage_trusted(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=build_embed("Manage Trusted Moderators", "Add or remove a member's trusted-moderator access."),
            view=TrustedManageView())

    @app_commands.command(name="jailperms", description="View jail permissions.")
    @app_commands.default_permissions(administrator=True)
    async def jailperms(self, interaction: discord.Interaction):
        embed = build_embed("Jail Permissions", "Choose what you'd like to view below.")
        await interaction.response.send_message(embed=embed, view=JailPermsView())


async def setup(bot: commands.Bot):
    await bot.add_cog(PermissionsCog(bot))
