const {
  PermissionFlagsBits,
  ChannelType,
} = require('discord.js');
const { db, now, getConfig } = require('./db');

function formatDuration(seconds) {
  if (seconds == null) return 'Permanent';
  seconds = Math.max(0, Number(seconds));
  if (seconds === 0) return '0s';

  const days = Math.floor(seconds / 86400);
  seconds %= 86400;
  const hours = Math.floor(seconds / 3600);
  seconds %= 3600;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;

  const parts = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  if (minutes) parts.push(`${minutes}m`);
  if (secs && parts.length < 2) parts.push(`${secs}s`);
  return parts.join(' ') || '0s';
}

function parseDuration(input) {
  if (!input) return null;
  const value = String(input).trim().toLowerCase();
  if (['permanent', 'perm', 'forever'].includes(value)) return null;

  const match = value.match(/^(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$/);
  if (!match) {
    throw new Error('Invalid duration. Use `30s`, `10m`, `2h`, `1d`, or `permanent`.');
  }

  const amount = Number(match[1]);
  if (!Number.isSafeInteger(amount) || amount <= 0) throw new Error('Duration must be greater than zero.');

  const unit = match[2];
  const multiplier = unit.startsWith('s') ? 1 : unit.startsWith('m') ? 60 : unit.startsWith('h') ? 3600 : 86400;
  const result = amount * multiplier;
  if (result > 365 * 86400) throw new Error('Maximum sentence duration is 365 days.');
  return result;
}

function isStaff(member) {
  if (!member) return false;
  return member.id === member.guild.ownerId || member.permissions.has(PermissionFlagsBits.Administrator) || member.permissions.has(PermissionFlagsBits.ManageRoles) || member.permissions.has(PermissionFlagsBits.ModerateMembers);
}

async function requireStaff(interaction) {
  if (isStaff(interaction.member)) return true;
  const { errorEmbed } = require('./embeds');
  const payload = { embeds: [errorEmbed('You do not have permission to use this command.')], ephemeral: true };
  if (interaction.replied || interaction.deferred) await interaction.followUp(payload);
  else await interaction.reply(payload);
  return false;
}

function remaining(caseRow) {
  if (caseRow.duration_seconds == null) return null;
  return Math.max(0, Number(caseRow.created_at) + Number(caseRow.duration_seconds) - now());
}

function mention(id) {
  return `<@${id}>`;
}

function getBotMember(guild) {
  return guild.members.me || guild.members.cache.get(guild.client.user.id);
}

async function jailMember(guild, member, moderator, reason, durationSeconds) {
  const cfg = getConfig(guild.id);
  const bot = getBotMember(guild);
  if (!bot) return { ok: false, message: 'I could not resolve my server member. Try again.' };
  if (!cfg.jail_role_id) return { ok: false, message: 'Jail role is not configured. Run `/jailsetup` first.' };
  if (!cfg.jail_category_id) return { ok: false, message: 'Jail category is not configured. Run `/jailsetup` first.' };

  const jailRole = guild.roles.cache.get(String(cfg.jail_role_id));
  const category = guild.channels.cache.get(String(cfg.jail_category_id));
  if (!jailRole) return { ok: false, message: 'Configured jail role no longer exists. Run `/jailsetup` again.' };
  if (!category || category.type !== ChannelType.GuildCategory) return { ok: false, message: 'Configured jail category no longer exists. Run `/jailsetup` again.' };
  if (!jailRole.editable) return { ok: false, message: 'My highest role must be above the configured jail role.' };
  if (!member.manageable) return { ok: false, message: 'I cannot manage that member. Move my bot role above the member or their roles.' };
  if (member.roles.cache.has(jailRole.id)) return { ok: false, message: 'That member already has the jail role.' };

  const caseId = db.nextCaseNumber(guild.id);
  const roleBackup = member.roles.cache
    .filter(role => role.id !== guild.id && !role.managed && role.editable)
    .map(role => role.id);

  let cell = null;
  try {
    if (roleBackup.length) await member.roles.remove(roleBackup, `Warden case #${caseId}`);
    await member.roles.add(jailRole, `Warden case #${caseId}`);

    cell = await guild.channels.create({
      name: `cell-${caseId}`,
      type: ChannelType.GuildText,
      parent: category.id,
      permissionOverwrites: [
        { id: guild.roles.everyone.id, deny: [PermissionFlagsBits.ViewChannel] },
        { id: jailRole.id, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory] },
        { id: member.id, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory] },
        { id: bot.id, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory, PermissionFlagsBits.ManageChannels, PermissionFlagsBits.ManageMessages] },
      ],
      reason: `Warden jail cell for case #${caseId}`,
    });

    db.insertCase({
      caseId,
      guildId: guild.id,
      userId: member.id,
      moderatorId: moderator.id,
      reason,
      createdAt: now(),
      durationSeconds,
      roleBackup: roleBackup.join(','),
      cellId: cell.id,
    });

    return { ok: true, caseId, cell };
  } catch (error) {
    if (cell) await cell.delete('Rolling back failed Warden jail').catch(() => {});
    await member.roles.remove(jailRole, 'Rolling back failed Warden jail').catch(() => {});
    if (roleBackup.length) await member.roles.add(roleBackup.map(id => guild.roles.cache.get(id)).filter(Boolean), 'Rolling back failed Warden jail').catch(() => {});
    console.error('jailMember failed:', error);
    return { ok: false, message: 'The jail action could not be completed. Check my role and channel permissions.' };
  }
}

async function releaseMember(guild, member, moderator, caseId, status = 'released') {
  const c = db.getActiveCaseByCase(guild.id, caseId);
  if (!c) return { ok: false, message: `Case #${caseId} is not currently active.` };

  const cfg = getConfig(guild.id);
  const jailRole = cfg.jail_role_id ? guild.roles.cache.get(String(cfg.jail_role_id)) : null;

  if (member) {
    if (!member.manageable && !member.permissions.has(PermissionFlagsBits.Administrator)) {
      return { ok: false, message: 'I cannot manage that member to release them.' };
    }
    if (jailRole && member.roles.cache.has(jailRole.id)) await member.roles.remove(jailRole, `Warden case #${caseId} closed`).catch(() => {});

    const roles = (c.role_backup || '').split(',')
      .filter(Boolean)
      .map(id => guild.roles.cache.get(id))
      .filter(role => role && !role.managed && role.editable);
    if (roles.length) await member.roles.add(roles, `Warden case #${caseId} role restoration`).catch(() => {});
  }

  if (c.cell_channel_id) {
    const channel = guild.channels.cache.get(String(c.cell_channel_id));
    if (channel) await channel.delete(`Warden case #${caseId} closed`).catch(() => {});
  }

  db.prepare('DELETE FROM cellmates WHERE guild_id = ? AND case_id = ?').run(String(guild.id), Number(caseId));
  db.prepare("UPDATE cell_visitations SET status = 'expired' WHERE guild_id = ? AND case_id = ? AND status = 'active'").run(String(guild.id), Number(caseId));
  db.closeCase(guild.id, caseId, status, moderator?.id || null);
  return { ok: true };
}

async function expireVisitations(client) {
  const rows = db.prepare("SELECT * FROM cell_visitations WHERE status = 'active' AND expires_at <= ?").all(now());
  for (const visit of rows) {
    const guild = client.guilds.cache.get(String(visit.guild_id));
    const channel = guild?.channels.cache.get(String(visit.channel_id));
    if (channel) await channel.permissionOverwrites.delete(String(visit.visitor_id), 'Warden visitation expired').catch(() => {});
    db.prepare("UPDATE cell_visitations SET status = 'expired' WHERE visitation_id = ?").run(visit.visitation_id);
  }
}

async function notifyAndLog(guild, { action, userId, moderatorId, caseId, detail, dmTarget, dmEmbed, logEmbed }) {
  db.logAction({ guildId: guild.id, action, userId, moderatorId, caseId, detail });
  if (dmTarget && dmEmbed) await dmTarget.send({ embeds: [dmEmbed] }).catch(() => {});
  const cfg = getConfig(guild.id);
  if (cfg.log_channel_id && logEmbed) {
    const channel = guild.channels.cache.get(String(cfg.log_channel_id));
    if (channel) await channel.send({ embeds: [logEmbed] }).catch(() => {});
  }
}

module.exports = {
  formatDuration, parseDuration, isStaff, requireStaff, remaining, mention,
  jailMember, releaseMember, expireVisitations, notifyAndLog,
};
