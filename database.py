"""
Async SQLite persistence layer for the Jail System bot.

Everything the bot needs to remember lives here: guild configuration,
jail cases, sentence timers, appeals, warnings, autojail rules,
trusted/exempt lists, and probation monitoring.

Using SQLite (a single file, jail.db) means the bot's state survives
restarts and redeploys on Railway as long as a persistent volume /
the working directory is preserved between deploys of the same service.
"""

import time
import aiosqlite

from config import DB_PATH

_db: aiosqlite.Connection | None = None


async def init_db() -> None:
    """Open the database connection and create tables if they don't exist."""
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(
        """
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            jail_role_id INTEGER,
            jail_category_id INTEGER,
            log_channel_id INTEGER,
            appeal_channel_id INTEGER,
            default_minutes INTEGER DEFAULT 60,
            dm_notifications INTEGER DEFAULT 1,
            auto_restore INTEGER DEFAULT 1,
            voice_mode TEXT DEFAULT 'disconnect'
        );

        CREATE TABLE IF NOT EXISTS jail_cases (
            case_id INTEGER NOT NULL,          -- same number as the cell channel; reused
                                                -- from the lowest free number once a case closes
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT,
            created_at INTEGER NOT NULL,
            duration_seconds INTEGER,          -- NULL = permanent
            remaining_seconds INTEGER,         -- used while frozen
            frozen INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',      -- active, released, pardoned, expired
            released_at INTEGER,
            released_by INTEGER,
            role_backup TEXT,                  -- comma separated role ids removed on jail
            evidence TEXT,
            notes TEXT,
            on_probation INTEGER DEFAULT 0,
            cell_channel_id INTEGER            -- per-user jail cell channel, deleted on release
        );

        -- Only one ACTIVE case may occupy a given case number per guild at a
        -- time. Once that case closes the number frees up and can be handed
        -- to the next person jailed, so historical rows are allowed to
        -- repeat a case_id (they just can't both be active at once).
        CREATE UNIQUE INDEX IF NOT EXISTS idx_jail_cases_active_number
            ON jail_cases (guild_id, case_id) WHERE status = 'active';

        CREATE TABLE IF NOT EXISTS jail_warnings (
            warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS appeals (
            appeal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'pending',     -- pending, approved, denied, withdrawn
            created_at INTEGER NOT NULL,
            decided_by INTEGER,
            decided_at INTEGER,
            channel_id INTEGER,
            message_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS trusted_moderators (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS exempt_entries (
            guild_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL,         -- role or user
            PRIMARY KEY (guild_id, entity_id, entity_type)
        );

        CREATE TABLE IF NOT EXISTS autojail_config (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            max_violations INTEGER DEFAULT 3,
            window_seconds INTEGER DEFAULT 60,
            default_minutes INTEGER DEFAULT 30
        );

        CREATE TABLE IF NOT EXISTS autojail_lists (
            guild_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            list_type TEXT NOT NULL,           -- whitelist or blacklist
            PRIMARY KEY (guild_id, entity_id, list_type)
        );

        CREATE TABLE IF NOT EXISTS action_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            case_id INTEGER,
            user_id INTEGER,
            moderator_id INTEGER,
            action TEXT NOT NULL,
            detail TEXT,
            created_at INTEGER NOT NULL
        );
        """
    )
    await _db.commit()

    # Migration: older databases were created before cell_channel_id existed.
    cur = await _db.execute("PRAGMA table_info(jail_cases)")
    columns = {row["name"] for row in await cur.fetchall()}
    if "cell_channel_id" not in columns:
        await _db.execute("ALTER TABLE jail_cases ADD COLUMN cell_channel_id INTEGER")
        await _db.commit()


def db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database has not been initialized yet.")
    return _db


async def close_db() -> None:
    if _db is not None:
        await _db.close()


def now() -> int:
    return int(time.time())


# ---------------------------------------------------------------------------
# Guild config helpers
# ---------------------------------------------------------------------------
async def get_guild_config(guild_id: int) -> aiosqlite.Row:
    cur = await db().execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
    row = await cur.fetchone()
    if row is None:
        await db().execute("INSERT INTO guild_config (guild_id) VALUES (?)", (guild_id,))
        await db().commit()
        cur = await db().execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
    return row


async def set_guild_config(guild_id: int, **fields) -> None:
    await get_guild_config(guild_id)  # ensure row exists
    keys = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [guild_id]
    await db().execute(f"UPDATE guild_config SET {keys} WHERE guild_id = ?", values)
    await db().commit()


async def next_case_number(guild_id: int) -> int:
    """
    Picks the lowest case number not currently in use by an active case in
    this guild. Case numbers double as the jailed member's cell channel
    number, and both are freed for reuse as soon as that case closes.
    """
    cur = await db().execute(
        "SELECT case_id FROM jail_cases WHERE guild_id = ? AND status = 'active'", (guild_id,)
    )
    used = {row["case_id"] for row in await cur.fetchall()}
    n = 1
    while n in used:
        n += 1
    return n


async def log_action(guild_id, action, user_id=None, moderator_id=None, case_id=None, detail=None):
    await db().execute(
        "INSERT INTO action_logs (guild_id, case_id, user_id, moderator_id, action, detail, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guild_id, case_id, user_id, moderator_id, action, detail, now()),
    )
    await db().commit()
