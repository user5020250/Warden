# Jail System Discord Bot

A discord.py moderation bot that implements a full "jail" system: role-based
jailing with timed sentences, cases, appeals decided by button instead of
command, autojail detection, statistics, logging, and a category-dropdown
`/help`. All embeds are pure black, and there are no emojis anywhere in the
bot's output.

## What changed from the original command list

**1. Command-naming conflicts.** Discord does not allow a slash command to be
both a standalone command and a group of subcommands at the same time. The
spec used `/jail` both as a direct action ("jail a member") and as a prefix
for many subcommands ("/jail extend", "/jail stats", "/jail role", etc).
Since jailing someone directly is the most important, most-used command, it
kept the name `/jail`, and the rest were organized into their own groups:

| Old (in the spec)               | New                  |
|----------------------------------|----------------------|
| `/jail list/info/history/search` | `/jailinfo ...`      |
| `/jail extend/reduce/settime/...`| `/sentence ...`      |
| `/jail warn/mute/nickname/...`   | `/jailmod ...`       |
| `/jail stats/top/moderators/...` | `/jailstats ...`     |
| `/jail role/logchannel/...`      | `/jailconfig ...`    |
| `/jail exempt/trusted/permissions`| `/jailperms ...`    |

`/case`, `/appeal`, `/cell`, `/autojail`, and `/logs` didn't have this
conflict and kept their original group names.

**2. Appeals now use buttons, not commands.** `/appeal accept` and
`/appeal deny` were removed. Every submitted appeal is posted as a black
embed in the appeal channel with **Approve** and **Decline** buttons.
Clicking Approve releases the member and restores their roles; clicking
Decline keeps them jailed. Only trusted moderators can use the buttons.

**3. Duplicates removed.** In the "Fun" category (renamed **Situational
Commands**, since the logic is meant to mirror real moderation, not be a
joke feature):
- `/parole` was removed — it was functionally identical to `/probation`
  (an early, conditional release).
- `/goodbehavior` was removed — it was functionally identical to
  `/sentence reduce` (reducing time remaining), just with a fixed reason.

`/solitary`, `/visitation`, and `/cellmate` were kept since each does
something the rest of the system doesn't.

**4. Removed per your instructions.** `/cell clean` and `/cell purge` are
gone. There is no jail voice channel and no voice-related commands
(`/jail disconnect`, `/jail movevc` do not exist in this build).

## Command reference

Run `/help` in Discord for the full, live, dropdown-based reference —
every command's name, what it does, exact usage, and the permission it
requires. The categories are: Setup, Basic Jail, Sentence Management,
Cases, Appeals, Jail Cell, Moderator Utilities, Auto Jail, Statistics,
Configuration, Permissions, Logging, and Situational Commands.

## How the logic works (real-world scenario mapping)

- **Jailing** strips a member's current roles (saved so they can be restored
  later), applies a single "Jailed" role, opens a case, DMs the member, and
  posts to the log channel — like being processed into custody.
- **Sentences** count down in real time via a background task; when time
  runs out the member is automatically released, same as an expiring
  sentence.
- **Freeze / resume** pause and resume the countdown, like a sentence being
  put on hold pending a hearing.
- **Appeals** work like a real appeals process: the appellant makes their
  case, staff review it in a dedicated channel, and a decision (Approve /
  Decline) is recorded and DMed to them.
- **Probation** releases someone early but flags the case for monitoring —
  if they reoffend, staff can see they were on probation and respond more
  strictly.
- **Solitary** is a harsher state on top of an existing jail sentence:
  messages are blocked even in the jail cell, and time is added.
- **Autojail** watches for rapid message spam and a banned-word list in
  real time and jails automatically once a violation threshold is crossed,
  the same way an automated system would flag repeated infractions.
- **Trusted moderators / exemptions** mirror a real permissions model:
  anyone with Manage Roles, Moderate Members, or Administrator can use jail
  commands by default; `/jailperms trusted add` extends that to specific
  people without changing their Discord permissions, and
  `/jailperms exempt add` protects specific roles or users from ever being
  jailed (e.g. bots, senior staff).

## Setup — GitHub

1. Create a new repository on GitHub (or use an existing one).
2. Download/copy this project's files into the repository folder.
3. From inside the folder:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: jail system bot"
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
3. Under **Bot**, enable these **Privileged Gateway Intents**:
   - Server Members Intent
   - Message Content Intent
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

This bot stores everything in a local SQLite file (`jail.db`). Railway's
filesystem is ephemeral on redeploy by default. If you want jail history,
cases, and configuration to survive redeploys, add a **Volume** to the
service in Railway (Service → Settings → Volumes) mounted at the project
directory, or point `DB_PATH` in `config.py` at a path inside that volume.

## Local development

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # then fill in DISCORD_TOKEN (and optionally DEV_GUILD_ID)
python bot.py
```

## Getting started in a server

1. Invite the bot with the OAuth2 URL from the Developer Portal steps
   above.
2. Run `/jailsetup` (Administrator only) to create the jail role, category,
   jail-cell channel, log channel, and appeal channel automatically.
3. Run `/jailperms trusted add` to give specific moderators access without
   changing their Discord role permissions, if needed.
4. Run `/help` to browse every command by category.
