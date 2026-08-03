import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import build_embed

TRUSTED = "Trusted Moderator (Manage Roles / Moderate Members / Administrator / trusted list)"
ADMIN = "Administrator"
EVERYONE = "Everyone"
OWNER = "Server Owner or Administrator"

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
                   "role, opens a case, and DMs the member. Usage: /jail member reason minutes.", TRUSTED),
        ("/unjail", "Releases a jailed member and restores their prior roles if auto-restore is on. "
                     "Usage: /unjail member.", TRUSTED),
        ("/forceunjail", "Strips the jail role and closes the case even if the case or role backup is missing "
                          "or broken. Usage: /forceunjail member [case_id].", TRUSTED),
        ("/selfrelease", "Lets the server owner or an administrator release themselves for debugging. "
                          "Usage: /selfrelease.", OWNER),
        ("/jailinfo list", "Lists everyone currently jailed with time remaining. Usage: /jailinfo list.", TRUSTED),
        ("/jailinfo info", "Shows the active case details for one member. Usage: /jailinfo info member.", TRUSTED),
        ("/jailinfo history", "Shows a member's full jail case history. Usage: /jailinfo history member.", TRUSTED),
        ("/jailinfo search", "Searches cases by member or case ID. Usage: /jailinfo search [member] [case_id].", TRUSTED),
    ],
    "Sentence Management": [
        ("/sentence extend", "Adds minutes to an active sentence. Usage: /sentence extend member minutes.", TRUSTED),
        ("/sentence reduce", "Removes minutes from an active sentence; releases the member if it hits zero. "
                              "Usage: /sentence reduce member minutes.", TRUSTED),
        ("/sentence settime", "Overwrites the remaining sentence with a new total. Usage: /sentence settime member minutes.", TRUSTED),
        ("/sentence permanent", "Converts an active sentence to permanent (manual release only). "
                                 "Usage: /sentence permanent member.", TRUSTED),
        ("/sentence pardon", "Fully forgives and closes an active sentence. Usage: /sentence pardon member.", TRUSTED),
        ("/sentence freeze", "Pauses the countdown on an active sentence. Usage: /sentence freeze member.", TRUSTED),
        ("/sentence resume", "Resumes a frozen sentence's countdown. Usage: /sentence resume member.", TRUSTED),
        ("/sentence restart", "Restarts the current sentence's timer from the beginning. Usage: /sentence restart member.", TRUSTED),
    ],
    "Cases": [
        ("/case view", "Shows full details for a case by ID. Usage: /case view case_id.", TRUSTED),
        ("/case editreason", "Changes a case's recorded reason. Usage: /case editreason case_id reason.", TRUSTED),
        ("/case editduration", "Changes a case's total duration. Usage: /case editduration case_id minutes.", TRUSTED),
        ("/case delete", "Permanently deletes a case record. Usage: /case delete case_id.", ADMIN),
        ("/case evidence", "Attaches evidence (a link or description) to a case. Usage: /case evidence case_id evidence.", TRUSTED),
        ("/case notes", "Adds a private note to a case, visible only to staff. Usage: /case notes case_id note.", TRUSTED),
        ("/case reopen", "Reopens a closed case and re-jails the member if they're still in the server. "
                          "Usage: /case reopen case_id.", TRUSTED),
    ],
    "Appeals": [
        ("/appeal submit", "Files an appeal for your own active case; posts it to the appeal channel with "
                            "Approve/Decline buttons for staff. Usage: /appeal submit message.", EVERYONE),
        ("/appeal view", "Shows the status of your most recent appeal. Usage: /appeal view.", EVERYONE),
        ("/appeal withdraw", "Cancels your own pending appeal. Usage: /appeal withdraw.", EVERYONE),
        ("/appeal list", "Lists all pending appeals in the server. Usage: /appeal list.", TRUSTED),
        ("/appeal close", "Closes a pending appeal without approving or denying it. Usage: /appeal close case_id.", TRUSTED),
        ("Approve / Decline buttons", "On every appeal embed in the appeal channel; moderators click these "
                                       "instead of using a command to approve (releases the member) or decline "
                                       "(keeps them jailed).", TRUSTED),
    ],
    "Jail Cell": [
        ("/cell lock", "Stops a specific jailed member from sending messages in their own cell channel. Usage: /cell lock member.", TRUSTED),
        ("/cell unlock", "Allows a specific jailed member to send messages in their own cell channel again. Usage: /cell unlock member.", TRUSTED),
        ("/cell announce", "Posts an announcement embed in a specific member's cell channel. Usage: /cell announce member message.", TRUSTED),
        ("/cell slowmode", "Sets slowmode delay (seconds) on a specific member's cell channel. Usage: /cell slowmode member seconds.", TRUSTED),
    ],
    "Moderator Utilities": [
        ("/jailmod warn", "Formally warns a jailed member and DMs them. Usage: /jailmod warn member reason.", TRUSTED),
        ("/jailmod mute", "Applies a Discord timeout on top of jail. Usage: /jailmod mute member minutes.", TRUSTED),
        ("/jailmod nickname", "Changes a jailed member's nickname. Usage: /jailmod nickname member nickname.", TRUSTED),
        ("/jailmod transfer", "Notes a case as transferred to a different category for record-keeping. "
                               "Usage: /jailmod transfer member category.", TRUSTED),
        ("/jailmod notify", "Resends the jail notification DM to a jailed member. Usage: /jailmod notify member.", TRUSTED),
        ("/jailmod restore", "Manually restores a member's pre-jail roles from the case's role backup. "
                              "Usage: /jailmod restore member.", TRUSTED),
    ],
    "Auto Jail": [
        ("/autojail enable", "Turns on automatic jailing for message spam and banned words. Usage: /autojail enable.", TRUSTED),
        ("/autojail disable", "Turns off automatic jailing. Usage: /autojail disable.", TRUSTED),
        ("/autojail violations", "Sets how many violations in a time window trigger an auto-jail. "
                                  "Usage: /autojail violations max_violations window_seconds.", TRUSTED),
        ("/autojail whitelist", "Exempts a role or user from autojail only. Usage: /autojail whitelist target.", TRUSTED),
        ("/autojail blacklist", "Marks a role or user to be auto-jailed on their very next violation. "
                                 "Usage: /autojail blacklist target.", TRUSTED),
        ("/autojail duration", "Sets the sentence length applied by automatic jailing. Usage: /autojail duration minutes.", TRUSTED),
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
        ("/jailconfig defaulttime", "Sets the default sentence length in minutes. Usage: /jailconfig defaulttime minutes.", ADMIN),
        ("/jailconfig dm", "Toggles whether jailed members are DMed. Usage: /jailconfig dm enabled.", ADMIN),
        ("/jailconfig autorestore", "Toggles automatic role restoration on release. Usage: /jailconfig autorestore enabled.", ADMIN),
        ("/jailconfig voicemode", "Sets how jailed members in voice are treated. Usage: /jailconfig voicemode mode.", ADMIN),
    ],
    "Permissions": [
        ("/jailperms exempt add", "Exempts a role or user from ever being jailed. Usage: /jailperms exempt add target.", ADMIN),
        ("/jailperms exempt remove", "Removes an exemption. Usage: /jailperms exempt remove target.", ADMIN),
        ("/jailperms trusted add", "Grants a member jail command access without needing Manage Roles. "
                                    "Usage: /jailperms trusted add member.", ADMIN),
        ("/jailperms trusted remove", "Revokes trusted-moderator access. Usage: /jailperms trusted remove member.", ADMIN),
        ("/jailperms permissions", "Shows the current trusted moderators and exemptions. Usage: /jailperms permissions.", ADMIN),
    ],
    "Logging": [
        ("/logs jail", "Shows the fifteen most recent jail log entries. Usage: /logs jail.", TRUSTED),
        ("/logs export", "Exports the full moderation log as a CSV file. Usage: /logs export.", TRUSTED),
        ("/logs clear", "Permanently deletes all jail logs for the server. Usage: /logs clear.", ADMIN),
        ("/logs search", "Searches logs by member or case ID. Usage: /logs search [member] [case_id].", TRUSTED),
    ],
    "Situational Commands": [
        ("/solitary", "Places a jailed member in stricter isolation, blocking messages even in the jail cell and "
                       "adding extra time. Usage: /solitary member minutes.", TRUSTED),
        ("/probation", "Releases a jailed member early, flags the case for monitoring, and restores roles. "
                        "Usage: /probation member reason.", TRUSTED),
        ("/visitation", "Temporarily grants a non-jailed member access to view and post in the jail cell. "
                         "Usage: /visitation visitor minutes.", TRUSTED),
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
