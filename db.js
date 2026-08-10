const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DB_PATH = process.env.DB_PATH || path.join(process.cwd(), 'data', 'warden.db');
const resolved = path.resolve(DB_PATH);
fs.mkdirSync(path.dirname(resolved), { recursive: true });

const db = new Database(resolved);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
CREATE TABLE IF NOT EXISTS guild_config (
  guild_id TEXT PRIMARY KEY,
  jail_role_id TEXT,
  jail_category_id TEXT,
  log_channel_id TEXT,
  default_seconds INTEGER NOT NULL DEFAULT 3600
);

CREATE TABLE IF NOT EXISTS case_counters (
  guild_id TEXT PRIMARY KEY,
  next_case_id INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS jail_cases (
  case_id INTEGER NOT NULL,
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  moderator_id TEXT NOT NULL,
  reason TEXT,
  created_at INTEGER NOT NULL,
  duration_seconds INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  released_at INTEGER,
  released_by TEXT,
  role_backup TEXT,
  cell_channel_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_jail_cases_guild_user ON jail_cases(guild_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jail_cases_guild_status ON jail_cases(guild_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS case_notes (
  note_id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  case_id INTEGER NOT NULL,
  moderator_id TEXT NOT NULL,
  note TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS case_evidence (
  evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  case_id INTEGER NOT NULL,
  moderator_id TEXT NOT NULL,
  url TEXT NOT NULL,
  filename TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS warnings (
  warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  moderator_id TEXT NOT NULL,
  reason TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
  report_id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  reporter_id TEXT NOT NULL,
  reported_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  evidence_url TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at INTEGER NOT NULL,
  closed_by TEXT,
  closed_at INTEGER,
  close_reason TEXT
);

CREATE TABLE IF NOT EXISTS appeals (
  appeal_id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  case_id INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at INTEGER NOT NULL,
  decided_by TEXT,
  decided_at INTEGER,
  decision_reason TEXT
);

CREATE TABLE IF NOT EXISTS cellmates (
  guild_id TEXT NOT NULL,
  case_id INTEGER NOT NULL,
  member_id TEXT NOT NULL,
  added_by TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY(guild_id, case_id, member_id)
);

CREATE TABLE IF NOT EXISTS cell_visitations (
  visitation_id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  visitor_id TEXT NOT NULL,
  occupant_id TEXT,
  case_id INTEGER,
  granted_by TEXT,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS action_logs (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  case_id INTEGER,
  user_id TEXT,
  moderator_id TEXT,
  action TEXT NOT NULL,
  detail TEXT,
  created_at INTEGER NOT NULL
);
`);

function now() {
  return Math.floor(Date.now() / 1000);
}

function getConfig(guildId) {
  const id = String(guildId);
  let row = db.prepare('SELECT * FROM guild_config WHERE guild_id = ?').get(id);
  if (!row) {
    db.prepare('INSERT INTO guild_config(guild_id) VALUES (?)').run(id);
    row = db.prepare('SELECT * FROM guild_config WHERE guild_id = ?').get(id);
  }
  return row;
}

function setConfig(guildId, fields) {
  getConfig(guildId);
  const allowed = new Set(['jail_role_id', 'jail_category_id', 'log_channel_id', 'default_seconds']);
  const entries = Object.entries(fields).filter(([key]) => allowed.has(key));
  if (!entries.length) return;
  const sql = `UPDATE guild_config SET ${entries.map(([key]) => `${key} = ?`).join(', ')} WHERE guild_id = ?`;
  db.prepare(sql).run(...entries.map(([, value]) => value), String(guildId));
}

function resetConfig(guildId) {
  db.prepare('DELETE FROM guild_config WHERE guild_id = ?').run(String(guildId));
}

const reserveCaseNumber = db.transaction((guildId) => {
  const id = String(guildId);
  db.prepare('INSERT OR IGNORE INTO case_counters(guild_id, next_case_id) VALUES (?, 1)').run(id);
  const row = db.prepare('SELECT next_case_id FROM case_counters WHERE guild_id = ?').get(id);
  db.prepare('UPDATE case_counters SET next_case_id = ? WHERE guild_id = ?').run(row.next_case_id + 1, id);
  return row.next_case_id;
});

function nextCaseNumber(guildId) {
  return reserveCaseNumber(guildId);
}

function getActiveCase(guildId, userId) {
  return db.prepare("SELECT * FROM jail_cases WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1").get(String(guildId), String(userId));
}

function getActiveCaseByCase(guildId, caseId) {
  return db.prepare("SELECT * FROM jail_cases WHERE guild_id = ? AND case_id = ? AND status = 'active' LIMIT 1").get(String(guildId), Number(caseId));
}

function getCase(guildId, caseId) {
  return db.prepare('SELECT * FROM jail_cases WHERE guild_id = ? AND case_id = ? ORDER BY created_at DESC LIMIT 1').get(String(guildId), Number(caseId));
}

function insertCase(c) {
  db.prepare(`
    INSERT INTO jail_cases
      (case_id, guild_id, user_id, moderator_id, reason, created_at, duration_seconds, status, role_backup, cell_channel_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
  `).run(
    Number(c.caseId), String(c.guildId), String(c.userId), String(c.moderatorId),
    c.reason || null, Number(c.createdAt), c.durationSeconds == null ? null : Number(c.durationSeconds),
    c.roleBackup || '', c.cellId || null
  );
}

function closeCase(guildId, caseId, status, by) {
  db.prepare(`
    UPDATE jail_cases
    SET status = ?, released_at = ?, released_by = ?, cell_channel_id = NULL
    WHERE guild_id = ? AND case_id = ? AND status = 'active'
  `).run(status, now(), by ? String(by) : null, String(guildId), Number(caseId));
}

function logAction(x) {
  db.prepare(`
    INSERT INTO action_logs(guild_id, case_id, user_id, moderator_id, action, detail, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(
    String(x.guildId), x.caseId == null ? null : Number(x.caseId),
    x.userId ? String(x.userId) : null, x.moderatorId ? String(x.moderatorId) : null,
    String(x.action), x.detail || null, now()
  );
}

module.exports = {
  db, now, getConfig, setConfig, resetConfig, nextCaseNumber,
  getActiveCase, getActiveCaseByCase, getCase, insertCase, closeCase, logAction
};
