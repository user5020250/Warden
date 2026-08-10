# Warden — Discord.js Edition

This is a Discord.js v14 port of the uploaded Warden moderation/jail bot, with the embed presentation rebuilt from the supplied **10 Custom Warden Embed Styles** reference.

## Embed design

The native Discord Embed API cannot draw arbitrary card borders, custom backgrounds, or a full CSS-like grid. The port therefore copies the reference's visual language using:

- black/near-black embed presentation
- a single strong accent color per action
- uppercase section/field labels
- compact 2–3 column inline fields
- short descriptions
- case IDs and values in code formatting
- consistent timestamp/footer
- distinct colors: red = jail, green = release, purple = jail status, blue = case/info, yellow = warning, green system = diagnostics/setup

## Included commands

- `/jail`
- `/unjail`
- `/forceunjail`
- `/jailstatus`
- `/jailinfo`
- `/sentence view|set|extend|reduce|end`
- `/case view|notes|evidence`
- `/caseinfo`
- `/warn`
- `/warnings list|info|delete|clear`
- `/report`
- `/reports`
- `/reportinfo`
- `/reportclose`
- `/appeal create|view|approve|deny|cancel`
- `/appeals`
- `/cell visit`
- `/cellmate list|add|remove`
- `/jailhistory`
- `/jailsearch`
- `/jaillogs`
- `/jailstats overview|top|moderators|activity|longest|oldest`
- `/jailsetup`
- `/jailconfig view|role|category|logchannel|defaulttime|reset`
- `/jaildiagnose`
- `/help`

## Setup

1. Install Node.js 20+.
2. Copy `.env.example` to `.env`.
3. Set `DISCORD_TOKEN` and `CLIENT_ID`.
4. Optionally set `DEV_GUILD_ID` for instant guild command registration.
5. Set `DB_PATH=/data/warden.db` when using a persistent Railway Volume.
6. Run `npm install`.
7. Run `node index.js`.

For a faster command refresh during development, set `DEV_GUILD_ID`.

## Important

Back up your existing SQLite database before switching implementations. The schema follows the uploaded Python bot's Warden tables, but database drivers and SQLite type handling differ between Python and Node.
