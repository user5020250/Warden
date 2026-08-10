const Database = require('better-sqlite3');
const path = require('path');
const DB_PATH = process.env.DB_PATH || 'warden.db';
const db = new Database(path.resolve(DB_PATH));
db.pragma('journal_mode = WAL');
db.exec(`
CREATE TABLE IF NOT EXISTS guild_config (guild_id TEXT PRIMARY KEY,jail_role_id TEXT,jail_category_id TEXT,log_channel_id TEXT,default_seconds INTEGER DEFAULT 3600);
CREATE TABLE IF NOT EXISTS jail_cases (case_id INTEGER NOT NULL,guild_id TEXT NOT NULL,user_id TEXT NOT NULL,moderator_id TEXT NOT NULL,reason TEXT,created_at INTEGER NOT NULL,duration_seconds INTEGER,status TEXT DEFAULT 'active',released_at INTEGER,released_by TEXT,role_backup TEXT,cell_channel_id TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jail_cases_active_number ON jail_cases(guild_id,case_id) WHERE status='active';
CREATE TABLE IF NOT EXISTS case_notes(note_id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,case_id INTEGER NOT NULL,moderator_id TEXT NOT NULL,note TEXT NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS case_evidence(evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,case_id INTEGER NOT NULL,moderator_id TEXT NOT NULL,url TEXT NOT NULL,filename TEXT,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS warnings(warning_id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,user_id TEXT NOT NULL,moderator_id TEXT NOT NULL,reason TEXT,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS reports(report_id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,reporter_id TEXT NOT NULL,reported_id TEXT NOT NULL,reason TEXT NOT NULL,evidence_url TEXT,status TEXT DEFAULT 'pending',created_at INTEGER NOT NULL,closed_by TEXT,closed_at INTEGER,close_reason TEXT);
CREATE TABLE IF NOT EXISTS appeals(appeal_id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,case_id INTEGER NOT NULL,user_id TEXT NOT NULL,reason TEXT NOT NULL,status TEXT DEFAULT 'pending',created_at INTEGER NOT NULL,decided_by TEXT,decided_at INTEGER,decision_reason TEXT);
CREATE TABLE IF NOT EXISTS cellmates(guild_id TEXT NOT NULL,case_id INTEGER NOT NULL,member_id TEXT NOT NULL,added_by TEXT NOT NULL,created_at INTEGER NOT NULL,PRIMARY KEY(guild_id,case_id,member_id));
CREATE TABLE IF NOT EXISTS cell_visitations(visitation_id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,channel_id TEXT NOT NULL,visitor_id TEXT NOT NULL,occupant_id TEXT,case_id INTEGER,granted_by TEXT,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS action_logs(log_id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,case_id INTEGER,user_id TEXT,moderator_id TEXT,action TEXT NOT NULL,detail TEXT,created_at INTEGER NOT NULL);
`);
function now(){return Math.floor(Date.now()/1000)}
function getConfig(guildId){let r=db.prepare('SELECT * FROM guild_config WHERE guild_id=?').get(String(guildId));if(!r){db.prepare('INSERT INTO guild_config(guild_id) VALUES(?)').run(String(guildId));r=db.prepare('SELECT * FROM guild_config WHERE guild_id=?').get(String(guildId));}return r}
function setConfig(guildId, fields){getConfig(guildId);const keys=Object.keys(fields);if(!keys.length)return;db.prepare(`UPDATE guild_config SET ${keys.map(k=>`${k}=?`).join(',')} WHERE guild_id=?`).run(...keys.map(k=>fields[k]),String(guildId))}
function resetConfig(guildId){db.prepare('DELETE FROM guild_config WHERE guild_id=?').run(String(guildId));getConfig(guildId)}
function nextCaseNumber(guildId){const used=new Set(db.prepare("SELECT case_id FROM jail_cases WHERE guild_id=? AND status='active'").all(String(guildId)).map(x=>x.case_id));let n=1;while(used.has(n))n++;return n}
function getActiveCase(guildId,userId){return db.prepare("SELECT * FROM jail_cases WHERE guild_id=? AND user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1").get(String(guildId),String(userId))}
function getActiveCaseByCase(guildId,caseId){return db.prepare("SELECT * FROM jail_cases WHERE guild_id=? AND case_id=? AND status='active'").get(String(guildId),caseId)}
function getCase(guildId,caseId){return db.prepare('SELECT * FROM jail_cases WHERE guild_id=? AND case_id=? ORDER BY created_at DESC LIMIT 1').get(String(guildId),caseId)}
function insertCase(c){db.prepare('INSERT INTO jail_cases(case_id,guild_id,user_id,moderator_id,reason,created_at,duration_seconds,role_backup,cell_channel_id) VALUES(?,?,?,?,?,?,?,?,?)').run(c.caseId,String(c.guildId),String(c.userId),String(c.moderatorId),c.reason||null,c.createdAt,c.durationSeconds,c.roleBackup,c.cellId)}
function closeCase(guildId,caseId,status,by){db.prepare('UPDATE jail_cases SET status=?,released_at=?,released_by=?,cell_channel_id=NULL WHERE guild_id=? AND case_id=?').run(status,now(),by?String(by):null,String(guildId),caseId)}
function logAction(x){db.prepare('INSERT INTO action_logs(guild_id,case_id,user_id,moderator_id,action,detail,created_at) VALUES(?,?,?,?,?,?,?)').run(String(x.guildId),x.caseId||null,x.userId?String(x.userId):null,x.moderatorId?String(x.moderatorId):null,x.action,x.detail||null,now())}
module.exports={db,now,getConfig,setConfig,resetConfig,nextCaseNumber,getActiveCase,getActiveCaseByCase,getCase,insertCase,closeCase,logAction};
