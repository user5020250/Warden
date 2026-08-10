# Warden — Discord.js v14

A professional Discord moderation and jail system built with Discord.js v14 and SQLite.

## Included commands

### Jail
- `/jail <member> [duration] [reason]`
- `/unjail <member>`
- `/jailstatus`
- `/jailinfo <member>`

### Sentence
- `/sentence view <member>`
- `/sentence set <member> <duration>`
- `/sentence extend <member> <duration>`
- `/sentence reduce <member> <duration>`
- `/sentence end <member>`

### Cases
- `/case view`
- `/case notes <case_id> <note>`
- `/case evidence <case_id> <url>`
- `/caseinfo <case_id>`
- `/jailhistory <member>`
- `/jailsearch <query>`
- `/jaillogs`

### Warnings
- `/warn <member> <reason>`
- `/warnings list <member>`
- `/warnings info <warning_id>`
- `/warnings delete <warning_id>`
- `/warnings clear <member>`

### Reports
- `/report <member> <reason> [evidence]`
- `/reports`
- `/reportinfo <report_id>`
- `/reportclose <report_id> [reason]`

### Appeals
- `/appeal create <case_id> <reason>`
- `/appeal view <appeal_id>`
- `/appeal approve <appeal_id> [reason]`
- `/appeal deny <appeal_id> [reason]`
- `/appeal cancel <appeal_id>`
- `/appeals`

### Cells
- `/cell visit <member> <visitor> <duration>`
- `/cellmate list <member>`
- `/cellmate add <member> <cellmate>`
- `/cellmate remove <member> <cellmate>`

### Statistics
- `/jailstats overview`
- `/jailstats top`
- `/jailstats moderators`
- `/jailstats activity`
- `/jailstats longest`
- `/jailstats oldest`

### Configuration
- `/jailsetup`
- `/jailconfig view`
- `/jailconfig role <role>`
- `/jailconfig category <category>`
- `/jailconfig logchannel <channel>`
- `/jailconfig defaulttime <duration>`
- `/jailconfig reset`
- `/jaildiagnose`
- `/help`

`/forceunjail` is intentionally not included.

## Local setup

```bash
npm install
cp .env.example .env
npm start
```

For instant command updates while developing, set `DEV_GUILD_ID` to your test server ID. For global commands, leave it blank.

## Railway

1. Connect the GitHub repository to Railway.
2. Add `DISCORD_TOKEN` in Railway Variables.
3. Add `CLIENT_ID` if you plan to run `npm run deploy` manually.
4. Mount a Railway Volume at `/data`.
5. Set `DB_PATH=/data/warden.db` in Railway Variables.
6. Deploy.

The SQLite database must live on the Volume if jail cases, roles, reports, warnings, and configuration must survive redeploys.
