import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import build_embed

STAFF = "Staff (Moderate Members / Manage Roles / Administrator)"
ADMIN = "Administrator"
EVERYONE = "Everyone"

# Static command reference. Kept separate from the live command tree so the
# descriptions here can include the exact permission model in plain English,
# and can note where a command was renamed from the original spec to avoid
# a Discord naming conflict.
CATEGORIES: dict[str, list[tuple[str, str, str]]] = {
    "Setup": [
        ("/jailsetup", "Automatically creates the jail role, jail category, and a single log channel used for "
                        "jail actions, warnings, reports, and appeal decisions, and links them together. "
                        "Individual cell channels are created per jailed member by /jail, not by this command. "
                        "Usage: /jailsetup.", ADMIN),
    ],
    "Basic Jail": [
        ("/jail", "Jails a member: strips their current roles (saved for later restoration), applies the jail "
                   "role, opens a case, creates a private cell channel, and DMs the member. The case ID matches "
                   "the member's cell channel number, and reuses the lowest free number once a case closes. "
                   "Usage: /jail member [duration] [reason] (duration defaults to the server default, e.g. "
                   "30s, 10m, 2hr, 1d, or permanent).", STAFF),
        ("/unjail", "Releases a jailed member, restores their prior roles, and deletes their cell channel. "
                     "Usage: /unjail member.", STAFF),
        ("/jailstatus", "Lists every member currently jailed with their remaining sentence. Usage: /jailstatus.", STAFF),
        ("/jailinfo", "Shows a member's current jail status: case ID, moderator, remaining sentence, reason, and "
                       "cell channel. Usage: /jailinfo member.", STAFF),
    ],
    "Sentence Management": [
        ("/sentence view", "Shows your own current sentence and remaining time. Usage: /sentence view.", EVERYONE),
        ("/sentence set", "Changes a member's sentence to a specific total duration. Usage: /sentence set member "
                           "duration.", STAFF),
        ("/sentence extend", "Adds additional time to an active sentence. Usage: /sentence extend member duration.", STAFF),
        ("/sentence reduce", "Removes time from an active sentence; releases the member if it reaches zero. "
                              "Usage: /sentence reduce member duration.", STAFF),
        ("/sentence end", "Immediately ends the member's sentence and releases them. Usage: /sentence end member.", STAFF),
    ],
    "Cases": [
        ("/caseinfo", "Displays complete information about a specific jail case: member, moderator, status, "
                       "duration, reason, moderator notes, and evidence. (This is the direct case lookup — it's "
                       "named /caseinfo rather than /case, since Discord doesn't allow /case to be both a direct "
                       "command and a subcommand group.) Usage: /caseinfo case_id.", STAFF),
        ("/case view", "Shows your own jail cases. Usage: /case view.", EVERYONE),
        ("/case notes add", "Adds an internal moderator note to a case. Usage: /case notes add case_id note.", STAFF),
        ("/case evidence add", "Attaches a file as evidence on a case. Usage: /case evidence add case_id attachment.", STAFF),
    ],
    "Reports": [
        ("/report", "Reports a member to moderators for review, with optional evidence. Usage: /report member "
                     "reason [evidence].", EVERYONE),
        ("/reports", "Lists pending and recent reports. Usage: /reports.", STAFF),
        ("/reportinfo", "Shows full details of a specific report. Usage: /reportinfo report_id.", STAFF),
        ("/reportclose", "Closes a report once it's been reviewed. Usage: /reportclose report_id [reason].", STAFF),
    ],
    "Warnings": [
        ("/warn", "Gives a member an official warning. Usage: /warn member reason.", STAFF),
        ("/warnings list", "Shows all warnings a member has received. (Renamed from the spec's bare \"/warnings "
                            "member\" to avoid the same standalone-vs-group naming conflict as /case and "
                            "/autojail.) Usage: /warnings list member.", STAFF),
        ("/warnings info", "Shows details about a specific warning. Usage: /warnings info warning_id.", STAFF),
        ("/warnings delete", "Deletes a warning. Usage: /warnings delete warning_id.", STAFF),
        ("/warnings clear", "Clears a member's entire warning history. Usage: /warnings clear member.", STAFF),
    ],
    "Appeals": [
        ("/appeal create", "Files an appeal for your own active case. Usage: /appeal create case_id reason.", EVERYONE),
        ("/appeal view", "Shows an appeal's details. You may view your own appeals; staff may view any. "
                          "Usage: /appeal view appeal_id.", EVERYONE),
        ("/appeal approve", "Approves an appeal and releases the member. Usage: /appeal approve appeal_id.", STAFF),
        ("/appeal deny", "Denies an appeal; the member remains jailed. Usage: /appeal deny appeal_id [reason].", STAFF),
        ("/appeal cancel", "Cancels your own pending appeal. Usage: /appeal cancel appeal_id.", EVERYONE),
        ("/appeals", "Lists all pending appeals. Usage: /appeals.", STAFF),
    ],
    "AutoJail": [
        ("/autojail", "Opens a panel with Enable/Disable buttons for AutoJail. Usage: /autojail.", STAFF),
        ("/autojailconfig settings", "Shows the current AutoJail configuration. (Config subcommands live under "
                                      "/autojailconfig rather than /autojail, for the same naming-conflict reason "
                                      "as /case and /warnings.) Usage: /autojailconfig settings.", ADMIN),
        ("/autojailconfig threshold", "Sets how many messages within the window trigger AutoJail. "
                                       "Usage: /autojailconfig threshold number.", ADMIN),
        ("/autojailconfig window", "Sets the rolling time window violations are counted in. "
                                    "Usage: /autojailconfig window duration.", ADMIN),
        ("/autojailconfig duration", "Sets the jail duration AutoJail applies. Usage: /autojailconfig duration duration.", ADMIN),
        ("/autojailconfig whitelist add", "Exempts a member from AutoJail. Usage: /autojailconfig whitelist add member.", ADMIN),
        ("/autojailconfig whitelist remove", "Removes a member's AutoJail exemption. Usage: /autojailconfig whitelist remove member.", ADMIN),
    ],
    "Cellmate & Visitation": [
        ("/cellmate list", "Shows the members sharing a jail cell. Usage: /cellmate list member.", STAFF),
        ("/cellmate add", "Gives a second member standing access to a jailed member's cell, until removed or the "
                           "case closes. Usage: /cellmate add member cellmate.", STAFF),
        ("/cellmate remove", "Removes a member from any shared cell(s) they have access to. Usage: /cellmate "
                              "remove member.", STAFF),
        ("/cell visit", "Grants a non-jailed member temporary access to a jail cell that expires automatically. "
                         "Usage: /cell visit member visitor duration.", STAFF),
    ],
    "Configuration": [
        ("/jailconfig view", "Displays the current Warden configuration. Usage: /jailconfig view.", ADMIN),
        ("/jailconfig role", "Sets the jail role. Usage: /jailconfig role role.", ADMIN),
        ("/jailconfig category", "Sets the jail-cell category. Usage: /jailconfig category category.", ADMIN),
        ("/jailconfig logchannel", "Sets the moderation log channel. Usage: /jailconfig logchannel channel.", ADMIN),
        ("/jailconfig defaulttime", "Sets the default jail duration. Usage: /jailconfig defaulttime duration.", ADMIN),
        ("/jailconfig reset", "Resets Warden configuration to its defaults. Usage: /jailconfig reset.", ADMIN),
    ],
    "Diagnostics": [
        ("/jailhistory", "Shows a member's complete jail history. Usage: /jailhistory member.", STAFF),
        ("/jailsearch", "Searches jail cases by case ID, member, moderator, or a word in the reason. "
                         "Usage: /jailsearch query.", STAFF),
        ("/jaillogs", "Shows recent jail-system events. Usage: /jaillogs.", STAFF),
        ("/jaildiagnose", "Checks Warden's configuration, database connection, roles, channels, cells, and cases "
                           "for problems. Usage: /jaildiagnose.", ADMIN),
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
            description_lines.append(f"**{name}**\n{desc}\nRequired permission: `{perm}`\n")
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
            "Warden Help",
            "Select a category from the dropdown below to see its commands, what each one does, how to use "
            "it, and what permission it requires.",
        )
        await interaction.response.send_message(embed=embed, view=HelpView())


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
