import os
import time
import logging
import aiosqlite

from config import DB_PATH, DEFAULT_JAIL_SECONDS, DEFAULT_AUTOJAIL_THRESHOLD, \
    DEFAULT_AUTOJAIL_WINDOW_SECONDS, DEFAULT_AUTOJAIL_DURATION_SECONDS

logger = logging.getLogger("warden")

_db: aiosqlite.Connection | None = None


async def init_db() -> None:
    """Open the database connection and create tables if they don't exist."""
    global _db

    # Logged on every boot so a redeploy's logs show exactly which file the
    # bot is using and whether it already existed (i.e. whether this boot
    # is reusing persisted data or starting from a blank database). If
    # DB_PATH isn't pointed at the mounted volume, "already existed: False"
    # here after every deploy is the tell.
    resolved_path = os.path.abspath(DB_PATH)
    already_existed = os.path.exists(DB_PATH)
    size = os.path.getsize(DB_PATH) if already_existed else 0
    logger.info(
        "Opening database at %s (DB_PATH=%r) — already existed: %s, size: %d bytes",
        resolved_path, DB_PATH, already_existed, size,
    )

    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            jail_role_id INTEGER,
            jail_category_id INTEGER,
            log_channel_id INTEGER,
            default_seconds INTEGER DEFAULT {DEFAULT_JAIL_SECONDS},
            autojail_enabled INTEGER DEFAULT 0,
            autojail_threshold INTEGER DEFAULT {DEFAULT_AUTOJAIL_THRESHOLD},
            autojail_window_seconds INTEGER DEFAULT {DEFAULT_AUTOJAIL_WINDOW_SECONDS},
            autojail_duration_seconds INTEGER DEFAULT {DEFAULT_AUTOJAIL_DURATION_SECONDS}
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
            status TEXT DEFAULT 'active',      -- active, released, expired
            released_at INTEGER,
            released_by INTEGER,
            role_backup TEXT,                  -- comma separated role ids removed on jail
            cell_channel_id INTEGER            -- per-user jail cell channel, deleted on release
        );

        -- Only one ACTIVE case may occupy a given case number per guild at a
        -- time. Once that case closes the number frees up and can be handed
        -- to the next person jailed, so historical rows are allowed to
        -- repeat a case_id (they just can't both be active at once).
        CREATE UNIQUE INDEX IF NOT EXISTS idx_jail_cases_active_number
            ON jail_cases (guild_id, case_id) WHERE status = 'active';

        CREATE TABLE IF NOT EXISTS case_notes (
            note_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS case_evidence (
            evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            filename TEXT,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS warnings (
            warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            reporter_id INTEGER NOT NULL,
            reported_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            evidence_url TEXT,
            status TEXT DEFAULT 'pending',     -- pending, closed
            created_at INTEGER NOT NULL,
            closed_by INTEGER,
            closed_at INTEGER,
            close_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS appeals (
            appeal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT DEFAULT 'pending',     -- pending, approved, denied, cancelled
            created_at INTEGER NOT NULL,
            decided_by INTEGER,
            decided_at INTEGER,
            decision_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS autojail_whitelist (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS cellmates (
            guild_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            added_by INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (guild_id, case_id, member_id)
        );

        CREATE TABLE IF NOT EXISTS cell_visitations (
            visitation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            visitor_id INTEGER NOT NULL,
            occupant_id INTEGER,
            case_id INTEGER,
            granted_by INTEGER,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            status TEXT DEFAULT 'active'       -- active, expired, revoked (channel gone)
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

    # --- Migration: backfill columns on a guild_config table that already
    # existed before these columns were added to the schema above.
    #
    # CREATE TABLE IF NOT EXISTS is a no-op if the table is already present,
    # so on a database created by an older version of this bot, guild_config
    # can be missing columns that the rest of the code (e.g. cogs/autojail.py)
    # assumes exist. Reading a missing column off an aiosqlite.Row raises
    # IndexError ("No item with that key"), not KeyError, which is what was
    # happening here. We check what columns actually exist and add anything
    # missing, so both fresh and pre-existing databases end up consistent.
    cur = await _db.execute("PRAGMA table_info(guild_config)")
    existing_columns = {row["name"] for row in await cur.fetchall()}

    guild_config_columns = {
        "jail_role_id": "INTEGER",
        "jail_category_id": "INTEGER",
        "log_channel_id": "INTEGER",
        "default_seconds": f"INTEGER DEFAULT {DEFAULT_JAIL_SECONDS}",
        "autojail_enabled": "INTEGER DEFAULT 0",
        "autojail_threshold": f"INTEGER DEFAULT {DEFAULT_AUTOJAIL_THRESHOLD}",
        "autojail_window_seconds": f"INTEGER DEFAULT {DEFAULT_AUTOJAIL_WINDOW_SECONDS}",
        "autojail_duration_seconds": f"INTEGER DEFAULT {DEFAULT_AUTOJAIL_DURATION_SECONDS}",
    }

    for column, definition in guild_config_columns.items():
        if column not in existing_columns:
            logger.info("Migrating guild_config: adding missing column %s", column)
            await _db.execute(f"ALTER TABLE guild_config ADD COLUMN {column} {definition}")

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


async def reset_guild_config(guild_id: int) -> None:
    await db().execute("DELETE FROM guild_config WHERE guild_id = ?", (guild_id,))
    await db().execute("INSERT INTO guild_config (guild_id) VALUES (?)", (guild_id,))
    await db().commit()


# ---------------------------------------------------------------------------
# Jail case helpers
# ---------------------------------------------------------------------------
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


async def get_active_case(guild_id: int, user_id: int) -> aiosqlite.Row | None:
    """The user's current active case in this guild, if any."""
    cur = await db().execute(
        "SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active'"
        " ORDER BY created_at DESC LIMIT 1",
        (guild_id, user_id),
    )
    return await cur.fetchone()


async def get_case(guild_id: int, case_id: int) -> aiosqlite.Row | None:
    """Most recent case row matching this case number, active or historical."""
    cur = await db().execute(
        "SELECT * FROM jail_cases WHERE guild_id = ? AND case_id = ? ORDER BY created_at DESC LIMIT 1",
        (guild_id, case_id),
    )
    return await cur.fetchone()


async def log_action(guild_id, action, user_id=None, moderator_id=None, case_id=None, detail=None):
    await db().execute(
        "INSERT INTO action_logs (guild_id, case_id, user_id, moderator_id, action, detail, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guild_id, case_id, user_id, moderator_id, action, detail, now()),
    )
    await db().commit()


# ---------------------------------------------------------------------------
# Cell visitation helpers (used for auto-revoke of temporary cell access)
# ---------------------------------------------------------------------------
async def add_visitation(guild_id, channel_id, visitor_id, occupant_id, case_id, granted_by, expires_at) -> int:
    cur = await db().execute(
        "INSERT INTO cell_visitations (guild_id, channel_id, visitor_id, occupant_id, case_id, granted_by,"
        " created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (guild_id, channel_id, visitor_id, occupant_id, case_id, granted_by, now(), expires_at),
    )
    await db().commit()
    return cur.lastrowid


async def get_expired_visitations() -> list[aiosqlite.Row]:
    cur = await db().execute(
        "SELECT * FROM cell_visitations WHERE status = 'active' AND expires_at <= ?", (now(),)
    )
    return await cur.fetchall()


async def close_visitation(visitation_id: int, status: str = "expired") -> None:
    await db().execute(
        "UPDATE cell_visitations SET status = ? WHERE visitation_id = ?", (status, visitation_id)
    )
    await db().commit()


async def clear_dead_cell_channel(guild_id: int, channel_id: int) -> None:
    """Called when a cell channel is deleted directly in Discord (not via
    /unjail), so the case row doesn't keep pointing at a channel that no
    longer exists, and any visitations tied to it are revoked."""
    await db().execute(
        "UPDATE jail_cases SET cell_channel_id = NULL WHERE guild_id = ? AND cell_channel_id = ? AND status = 'active'",
        (guild_id, channel_id),
    )
    await db().execute(
        "UPDATE cell_visitations SET status = 'revoked' WHERE guild_id = ? AND channel_id = ? AND status = 'active'",
        (guild_id, channel_id),
    )
    await db().commit()
