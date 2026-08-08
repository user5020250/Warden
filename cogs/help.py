import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import build_embed

TRUSTED = "Trusted Moderator (Manage Roles / Moderate Members / Administrator / trusted list)"
ADMIN = "Administrator"
EVERYONE = "Everyone"

# Static command reference. Kept separate from the live command tree so the
# descriptions here can include the exact permission model in plain English.
CATEGORIES: dict[str, list[tuple[str, str, str]]] = {
    "Setup": [
        ("/jailsetup", "Automatically creates the jail role, jail category, log channel, and appeal channel, "
                        "and links them together. Individual cell channels are created per jailed member by "
                        "/jail, not by this command.", ADMIN),
    ],
    "Basic Jail": [
        ("/jail", "Jails a member: strips their current roles (saved for later restoration), applies the jail "
                   "role, opens a case, and DMs the member. The case ID matches the member's cell channel "
                   "number, and reuses the lowest free number once a case closes. Usage: /jail member reason "
                   "duration (e.g. 30s, 10m, 2hr, 1d, or permanent — omit for the server default).", TRUSTED),
        ("/release", "Releases a jailed member and restores their prior roles if auto-restore is on. "
                      "Usage: /release member reason.", TRUSTED),
        ("/jailinfo", "Opens a dropdown to browse jail records: List shows everyone currently jailed "
                       "(member, time remaining, reason, evidence, case ID); History lets you pick a member "
                       "and shows their complete jail case history. Usage: /jailinfo.", TRUSTED),
    ],
    "Sentence Management": [
        ("/sentence", "Opens an embed with buttons for an active sentence — Extend, Reduce, and Set Time — "
                       "each opens a popup asking for a duration (e.g. 30s, 10m, 2hr, 1d; Set Time also accepts "
                       "'permanent'). Reduce releases the member if it reaches zero. Usage: /sentence member.", TRUSTED),
    ],
    "Appeals": [
        ("/appeal submit", "Files an appeal for your own active case; posts it to the appeal channel with "
                            "Approve/Decline buttons for staff. You may only have one appeal open per case at "
                            "a time — you can submit again only after a previous appeal for that case was "
                            "declined. Usage: /appeal submit message.", EVERYONE),
        ("/appeal view", "Shows the status of your most recent appeal. Usage: /appeal view.", EVERYONE),
        ("/appeal withdraw", "Cancels your own pending appeal. Usage: /appeal withdraw.", EVERYONE),
        ("/appeal list", "Lists all pending appeals in the server. Usage: /appeal list.", TRUSTED),
        ("Approve / Decline buttons", "On every appeal embed in the appeal channel; moderators click these "
                                       "instead of using a command to approve (releases the member) or decline "
                                       "(keeps them jailed).", TRUSTED),
    ],
    "Jail Cell": [
        ("/cell lock", "Stops a specific jailed member from sending messages in their own cell channel. Usage: /cell lock member.", TRUSTED),
        ("/cell unlock", "Allows a specific jailed member to send messages in their own cell channel again. Usage: /cell unlock member.", TRUSTED),
        ("/cell slowmode", "Sets slowmode delay (seconds) on a specific member's cell channel. Usage: /cell slowmode member seconds.", TRUSTED),
    ],
    "Moderator Utilities": [
        ("/jailmod transfer", "Moves a jailed member to a different cell channel you choose, transferring their "
                               "channel access. Usage: /jailmod transfer member channel. (This lives under "
                               "/jailmod rather than /jail — Discord doesn't allow /jail to be both a direct "
                               "command and a subcommand group.)", TRUSTED),
        ("/jailmod notify", "Resends the jail notification DM to a jailed member. Usage: /jailmod notify member.", TRUSTED),
        ("/jailmod history", "Paginated (5 per page, with Previous/Next/Close buttons) view of every member "
                              "who's ever had a case: total cases, time served, last reason, and whether they're "
                              "currently active, sorted by most jailed. Usage: /jailmod history.", TRUSTED),
    ],
    "Statistics": [
        ("/jailstats overview", "Shows total cases, active cases, pardons, and unique members jailed. "
                                 "Usage: /jailstats overview.", TRUSTED),
        ("/jailstats top", "Shows the ten most frequently jailed members. Usage: /jailstats top.", TRUSTED),
        ("/jailstats moderators", "Shows the ten most active moderators by case count. Usage: /jailstats moderators.", TRUSTED),
        ("/jailstats activity", "Shows the ten most recent jail actions. Usage: /jailstats activity.", TRUSTED),
        ("/jailstats longest", "Shows the longest currently active sentences. Usage: /jailstats longest.", TRUSTED),
        ("/jailstats oldest", "Shows the oldest jail case records. Usage: /jailstats oldest.", TRUSTED),
    ],
    "Configuration": [
        ("/jailconfig role", "Sets the role used to mark jailed members. Usage: /jailconfig role role.", ADMIN),
        ("/jailconfig logchannel", "Sets the channel jail actions are logged to. Usage: /jailconfig logchannel channel.", ADMIN),
        ("/jailconfig appealchannel", "Sets the channel appeals are posted to. Usage: /jailconfig appealchannel channel.", ADMIN),
        ("/jailconfig category", "Sets the category that holds the jail channels. Usage: /jailconfig category category.", ADMIN),
        ("/jailconfig defaulttime", "Sets the default sentence duration. Usage: /jailconfig defaulttime duration "
                                     "(e.g. 30s, 10m, 2hr, 1d).", ADMIN),
        ("/jailconfig autorestore", "Toggles automatic role restoration on release. Usage: /jailconfig autorestore enabled.", ADMIN),
    ],
    "Permissions": [
        ("/jailperms", "Shows the current trusted moderators and exemptions. Usage: /jailperms.", ADMIN),
        ("/jailpermsmanage exempt add", "Exempts a role or user from ever being jailed. Usage: /jailpermsmanage exempt add target.", ADMIN),
        ("/jailpermsmanage exempt remove", "Removes an exemption. Usage: /jailpermsmanage exempt remove target.", ADMIN),
        ("/jailpermsmanage trusted add", "Grants a member jail command access without needing Manage Roles. "
                                          "Usage: /jailpermsmanage trusted add member.", ADMIN),
        ("/jailpermsmanage trusted remove", "Revokes trusted-moderator access. Usage: /jailpermsmanage trusted remove member.", ADMIN),
    ],
    "Logging": [
        ("/logs jail", "Shows the fifteen most recent jail log entries. Usage: /logs jail.", TRUSTED),
        ("/logs export", "Exports the full moderation log as a CSV file. Usage: /logs export.", TRUSTED),
        ("/logs clear", "Permanently deletes all jail logs for the server. Usage: /logs clear.", ADMIN),
        ("/logs search", "Searches logs by member or case ID. Usage: /logs search [member] [case_id].", TRUSTED),
    ],
    "Situational Commands": [
        ("/solitary", "Places a jailed member in stricter isolation, blocking messages even in the jail cell and "
                       "adding extra time. Usage: /solitary member duration (e.g. 30s, 10m, 2hr, 1d).", TRUSTED),
        ("/probation", "Releases a jailed member early, flags the case for monitoring, and restores roles. "
                        "Usage: /probation member reason.", TRUSTED),
        ("/visitation", "Temporarily grants a non-jailed member access to view and post in a jail cell. "
                         "Usage: /visitation member channel duration (e.g. 30s, 15m, 2hr, 1d).", TRUSTED),
        ("/cellmate", "Jails a second member into the same case context as an already-jailed member, matching "
                       "their remaining sentence. Usage: /cellmate member cellmate.", TRUSTED),
    ],
}


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=cat, value=cat) for cat in CATEGORIES]
        super().__init__(placeholder="Choose a command category", options=options, custom_id="help_category_select")

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        entries = CATEGORIES[category]
        description_lines = []
        for name, desc, perm in entries:
            description_lines.append(f"**{name}**\n{desc}\nRequired permission: {perm}\n")
        embed = build_embed(f"Help — {category}", "\n".join(description_lines))
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(HelpSelect())


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Shows all commands, grouped by category.")
    async def help_command(self, interaction: discord.Interaction):
        embed = build_embed(
            "Jail System Help",
            "Select a category from the dropdown below to see its commands, "
            "what each one does, how to use it, and what permission it requires.",
        )
        await interaction.response.send_message(embed=embed, view=HelpView())


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
