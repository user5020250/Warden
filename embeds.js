const { EmbedBuilder } = require('discord.js');

const COLORS = {
  black: 0x000000,
  jail: 0xff3030,
  release: 0x43d17a,
  status: 0x9b5cff,
  info: 0x3d8bfd,
  warning: 0xffc107,
  system: 0x36d66b,
  neutral: 0x7f8792,
  error: 0xff4d4d,
};

const FOOTER = 'WARDEN  •  MODERATION SYSTEM';

function base(title, description = null, color = COLORS.black) {
  const embed = new EmbedBuilder()
    .setColor(color)
    .setTitle(title)
    .setFooter({ text: FOOTER })
    .setTimestamp();

  if (description) embed.setDescription(description);
  return embed;
}

function field(name, value, inline = false) {
  return {
    name: String(name).toUpperCase(),
    value: String(value ?? '—').slice(0, 1024),
    inline,
  };
}

function addFields(embed, fields = []) {
  if (fields.length) embed.addFields(...fields.map(item => field(item[0], item[1], item[2] ?? false)));
  return embed;
}

function actionEmbed({ title, member, caseId, duration, reason, moderator, cell, color }) {
  const embed = base(title, member || null, color);
  addFields(embed, [
    ['Case ID', caseId ? `#${caseId}` : '—', true],
    ['Duration', duration ?? 'Permanent', true],
    ...(cell ? [['Cell', cell, true]] : []),
    ['Reason', reason || 'No reason provided', false],
    ...(moderator ? [['Moderator', moderator, true]] : []),
  ]);
  return embed;
}

function jailEmbed(data) {
  return actionEmbed({ ...data, title: 'MEMBER JAILED', color: COLORS.jail });
}

function unjailEmbed(data) {
  return actionEmbed({ ...data, title: 'MEMBER RELEASED', color: COLORS.release });
}

function jailInfoEmbed({ member, status, caseId, sentence, remaining, cell, moderator, jailedAt, reason }) {
  const embed = base('JAIL INFORMATION', member || null, COLORS.info);
  addFields(embed, [
    ['Status', status || '—', true],
    ['Case ID', caseId ? `#${caseId}` : '—', true],
    ['Sentence', sentence || '—', true],
    ['Remaining', remaining || '—', true],
    ['Cell', cell || 'None', true],
    ['Jailed By', moderator || '—', true],
    ['Jailed At', jailedAt || '—', true],
    ['Reason', reason || 'No reason provided', false],
  ]);
  return embed;
}

function statusEmbed(lines, page = 1, totalPages = 1) {
  const embed = base('CURRENTLY JAILED', null, COLORS.status);
  embed.setDescription(lines.length ? lines.join('\n\n') : 'No members are currently jailed.');
  if (totalPages > 1) embed.setFooter({ text: `${FOOTER}  •  PAGE ${page}/${totalPages}` });
  return embed;
}

function dashboardEmbed(stats) {
  const embed = base('WARDEN DASHBOARD', null, COLORS.system);
  addFields(embed, [
    ['Active Cases', stats.active ?? '—', true],
    ['Total Cases', stats.total ?? '—', true],
    ['Total Warnings', stats.warnings ?? '—', true],
    ['Appeals Pending', stats.appeals ?? '—', true],
    ['Top Moderator', stats.topModerator ?? '—', false],
    ['Most Jailed', stats.mostJailed ?? '—', false],
  ]);
  return embed;
}

function errorEmbed(message) {
  return base('ACTION FAILED', message, COLORS.error);
}

function successEmbed(title, description, fields = []) {
  return addFields(base(title, description, COLORS.release), fields);
}

function warningEmbed(title, description, fields = []) {
  return addFields(base(title, description, COLORS.warning), fields);
}

function systemEmbed(title, description, fields = []) {
  return addFields(base(title, description, COLORS.system), fields);
}

function infoEmbed(title, description, fields = []) {
  return addFields(base(title, description, COLORS.info), fields);
}

module.exports = {
  COLORS,
  base,
  field,
  addFields,
  jailEmbed,
  unjailEmbed,
  jailInfoEmbed,
  statusEmbed,
  dashboardEmbed,
  errorEmbed,
  successEmbed,
  warningEmbed,
  systemEmbed,
  infoEmbed,
};
