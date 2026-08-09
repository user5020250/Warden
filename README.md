# Warden — Discord Moderation Bot

A discord.py moderation bot built around a full "jail" system: role-based
jailing with timed sentences, cases (with moderator notes and evidence),
warnings, reports, appeals, AutoJail, cellmates and cell visitations,
diagnostics, and a category-dropdown `/help`. Every embed is pure black
with bold field names and backtick-formatted values, and there are no
emojis anywhere in the bot's output.

## What changed from the original command list

**1. Command-naming conflicts.** Discord does not allow a slash command to
be both a standalone command and a group of subcommands at the same time.
Three places in the spec ran into this:

| Old (in the spec)                          | New                         |
|---------------------------------------------|------------------------------|
| `/case <case_id>` + `/case view/notes/evidence` | `/caseinfo <case_id>` + `/case view` / `/case notes add` / `/case evidence add` |
| `/warning <warning_id>` + `/warning delete`, `/warnings <member>` + `/warnings clear` | Consolidated into one group: `/warnings list/info/delete/clear` |
| `/autojail` (panel) + `/autojail settings/threshold/window/duration/whitelist` | `/autojail` (panel) stays; config moved to `/autojailconfig settings/threshold/window/duration/whitelist add/remove` |

**2. Single log channel.** The spec's `/jailconfig` only defines one
channel (`logchannel`), so jail actions, warnings, reports, and appeal
decisions all post to that same channel rather than each having their own.

**3. AutoJail detection.** The spec describes a threshold and a counting
window but not what counts as a "violation." This build treats **message
rate** as the violation: if a member sends `threshold` or more messages
within the rolling `window`, they're jailed automatically for the
configured AutoJail duration. Staff and whitelisted members are exempt.

**4. No separate trusted-moderator list.** Every staff-gated command
checks for the real Discord permissions Moderate Members, Manage Roles, or
Administrator (or being the server owner) — there's no separate
allow-list to manage on top of that.

**5. Appeals and report review are command-driven, not button-driven.**
The spec lists `/appeal approve/deny` and `/reportclose` as commands
(unlike an accept/decline-button flow), so that's how they're implemented
here. `/autojail`'s enable/disable panel is the one place the spec asks
for buttons, and that's the one place this build uses them.

## Command reference

Run `/help` in Discord for the full, live, dropdown-based reference —
every command's name, what it does, exact usage, and the permission it
requires. The categories are: Setup, Basic Jail, Sentence Management,
Cases, Reports, Warnings, Appeals, AutoJail, Cellmate & Visitation,
Configuration, and Diagnostics.

## How the logic works (real-world scenario mapping)

- **Jailing** strips a member's current roles (saved so they can be
  restored later), applies a single "Jailed" role, opens a case, creates a
  private cell channel, and DMs the member — like being processed into
  custody.
- **Sentences** count down in real time via a background task; when time
  runs out the member is automatically released, same as an expiring
  sentence.
- **Cases** carry a running record of moderator notes and evidence
  attachments, like an incident file that gets added to over time.
- **Reports** let any member flag another member for staff review;
  `/reportclose` is the record of that review having happened.
- **Warnings** are a lighter-weight record than a full case — no role
  change, just a logged note tied to the member.
- **Appeals** work like a real appeals process: the appellant makes their
  case, staff review it, and a decision (Approve/Deny) is recorded and
  DMed to them.
- **AutoJail** watches message rate in real time and jails automatically
  once a member crosses the configured threshold within the configured
  window, the same way an automated system would flag a burst of
  activity.
- **Cellmate** gives a second member standing access to someone's cell
  (until removed or the case closes); **cell visit** is the temporary,
  self-expiring version of the same idea.
- **Diagnostics** (`/jaildiagnose`) checks that the configured role,
  category, and log channel still exist, that the bot has the
  permissions it needs, and that active cases aren't pointing at members
  who've left or cell channels that no longer exist.

## Setup — GitHub

1. Create a new repository on GitHub (or use an existing one).
2. Download/copy this project's files into the repository folder.
3. From inside the folder:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Warden"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```
   `.env` is already listed in `.gitignore`, so your bot token will not be
   committed.

## Setup — Discord Developer Portal

1. Go to https://discord.com/developers/applications and create a new
   application (or use an existing one).
2. Under **Bot**, click **Reset Token** and copy it — this is your
   `DISCORD_TOKEN`.
3. Under **Bot**, enable the **Server Members Intent** (privileged gateway
   intent) — it's used to look up members by name in `/jailsearch` and to
   resolve members elsewhere.
4. Under **OAuth2 → URL Generator**, select the `bot` and
   `applications.commands` scopes, and at minimum these bot permissions:
   Manage Roles, Manage Channels, Send Messages, Embed Links, Manage
   Messages, Moderate Members, Read Message History. Use the generated URL
   to invite the bot to your server.

## Setup — Railway

1. Go to https://railway.app and create a new project.
2. Choose **Deploy from GitHub repo** and select the repository you pushed
   above. (You may need to connect your GitHub account to Railway first.)
3. Railway will detect `requirements.txt` and `railway.json` automatically
   via Nixpacks — no extra build configuration is needed.
4. Open the new service's **Variables** tab and add:
   - `DISCORD_TOKEN` — the bot token from the Developer Portal.
   - `DEV_GUILD_ID` — *(optional)* your test server's ID, for instant slash
     command syncing while you're setting things up. Remove this once
     you're ready for the bot to be used across multiple servers, since
     global command sync can take up to an hour to propagate but works
     everywhere.
5. Deploy. Railway will run `python bot.py` as defined in `railway.json`
   / `Procfile`.
6. Check the **Deployments → Logs** tab — you should see
   `Logged in as <YourBot>#0000` once it's running.

### Persisting data between deploys

This bot stores everything in a local SQLite file (`warden.db`). Railway's
filesystem is ephemeral on redeploy by default. If you want jail history,
cases, warnings, reports, and configuration to survive redeploys, add a
**Volume** to the service in Railway (Service → Settings → Volumes), then
set the `DB_PATH` variable to a path inside that volume (e.g.
`/data/warden.db`).

## Local development

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp env.example .env        # then fill in DISCORD_TOKEN (and optionally DEV_GUILD_ID)
python bot.py
```

## Getting started in a server

1. Invite the bot with the OAuth2 URL from the Developer Portal steps
   above.
2. Run `/jailsetup` (Administrator only) to create the jail role,
   category, and log channel automatically.
3. Run `/help` to browse every command by category.
