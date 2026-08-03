import discord
from discord import app_commands
from discord.ext import commands

from database import db
from utils.embeds import build_embed, error_embed


class PermissionsCog(commands.Cog):
    """Exemptions and trusted-moderator management. Grouped under /jailperms."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    jailperms = app_commands.Group(name="jailperms", description="Manage jail system permissions.",
                                    default_permissions=discord.Permissions(administrator=True))
    exempt = app_commands.Group(name="exempt", parent=jailperms, description="Manage jail exemptions.")
    trusted = app_commands.Group(name="trusted", parent=jailperms, description="Manage trusted moderators.")

    @exempt.command(name="add", description="Exempt a role or user from being jailed.")
    @app_commands.describe(target="The role or user to exempt")
    async def exempt_add(self, interaction: discord.Interaction, target: discord.Role | discord.Member):
        entity_type = "role" if isinstance(target, discord.Role) else "user"
        await db().execute(
            "INSERT OR IGNORE INTO exempt_entries (guild_id, entity_id, entity_type) VALUES (?, ?, ?)",
            (interaction.guild.id, target.id, entity_type),
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Exemption Added", f"{target.mention} can no longer be jailed."))

    @exempt.command(name="remove", description="Remove exemption.")
    @app_commands.describe(target="The role or user to remove exemption from")
    async def exempt_remove(self, interaction: discord.Interaction, target: discord.Role | discord.Member):
        entity_type = "role" if isinstance(target, discord.Role) else "user"
        result = await db().execute(
            "DELETE FROM exempt_entries WHERE guild_id = ? AND entity_id = ? AND entity_type = ?",
            (interaction.guild.id, target.id, entity_type),
        )
        await db().commit()
        if result.rowcount == 0:
            return await interaction.response.send_message(embed=error_embed(f"{target.mention} was not exempt."))
        await interaction.response.send_message(embed=build_embed("Exemption Removed", f"{target.mention} can be jailed again."))

    @trusted.command(name="add", description="Add trusted moderator.")
    @app_commands.describe(member="The member to trust with jail commands")
    async def trusted_add(self, interaction: discord.Interaction, member: discord.Member):
        await db().execute(
            "INSERT OR IGNORE INTO trusted_moderators (guild_id, user_id) VALUES (?, ?)",
            (interaction.guild.id, member.id),
        )
        await db().commit()
        await interaction.response.send_message(embed=build_embed("Trusted Moderator Added", f"{member.mention} can now use jail commands."))

    @trusted.command(name="remove", description="Remove trusted moderator.")
    @app_commands.describe(member="The member to remove from the trusted list")
    async def trusted_remove(self, interaction: discord.Interaction, member: discord.Member):
        result = await db().execute(
            "DELETE FROM trusted_moderators WHERE guild_id = ? AND user_id = ?",
            (interaction.guild.id, member.id),
        )
        await db().commit()
        if result.rowcount == 0:
            return await interaction.response.send_message(embed=error_embed(f"{member.mention} was not a trusted moderator."))
        await interaction.response.send_message(embed=build_embed("Trusted Moderator Removed", f"{member.mention} no longer has jail command access."))

    @jailperms.command(name="permissions", description="View jail permissions.")
    async def view_permissions(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cur = await db().execute("SELECT user_id FROM trusted_moderators WHERE guild_id = ?", (interaction.guild.id,))
        trusted_rows = await cur.fetchall()
        cur = await db().execute("SELECT entity_id, entity_type FROM exempt_entries WHERE guild_id = ?", (interaction.guild.id,))
        exempt_rows = await cur.fetchall()
        trusted_text = "\n".join(f"<@{r['user_id']}>" for r in trusted_rows) or "None"
        exempt_text = "\n".join(
            f"<@&{r['entity_id']}>" if r["entity_type"] == "role" else f"<@{r['entity_id']}>" for r in exempt_rows
        ) or "None"
        embed = build_embed("Jail Permissions", None, fields=[
            ("Trusted Moderators", trusted_text, False),
            ("Exempt Roles/Users", exempt_text, False),
            ("Note", "Members with Manage Roles, Moderate Members, Administrator, or who own the server "
                     "can always use jail commands even if not listed above.", False),
        ])
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PermissionsCog(bot))
