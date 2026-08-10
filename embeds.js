const { EmbedBuilder } = require('discord.js');

// Discord cannot reproduce arbitrary CSS/card borders inside a native embed.
// These builders reproduce the reference image's visual language using the
// native embed color bar, uppercase headings, compact fields, timestamps,
// black presentation, and consistent Warden footer.
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
  const e = new EmbedBuilder()
    .setColor(color)
    .setTitle(title)
    .setTimestamp()
    .setFooter({ text: FOOTER });
  if (description) e.setDescription(description);
  return e;
}

function field(name, value, inline = false) {
  return { name: name.toUpperCase(), value: String(value ?? '—'), inline };
}

function addFields(embed, fields = []) {
  embed.addFields(...fields.map(f => field(f[0], f[1], f[2] ?? false)));
  return embed;
}

function actionEmbed({title, member, caseId, duration, reason, moderator, cell, color = COLORS.jail}) {
  const e = base(title, null, color);
  addFields(e, [
    ['Member', member, true],
    ['Case ID', caseId ? `#${caseId}` : '—', true],
    ['Duration', duration ?? 'Permanent', true],
    ...(cell ? [['Cell', cell, true]] : []),
    ['Reason', reason || 'No reason provided', false],
    ...(moderator ? [['Moderator', moderator, true]] : []),
  ]);
  return e;
}

function jailEmbed(data) { return actionEmbed({...data, title: 'MEMBER JAILED', color: COLORS.jail}); }
function unjailEmbed(data) { return actionEmbed({...data, title: 'MEMBER RELEASED', color: COLORS.release}); }

function jailInfoEmbed({member, status, caseId, sentence, remaining, cell, moderator, jailedAt, reason}) {
  const e = base('JAIL INFORMATION', null, COLORS.info);
  e.setDescription(`${member}`);
  addFields(e, [
    ['Status', status || 'JAILED', true],
    ['Case ID', caseId ? `#${caseId}` : '—', true],
    ['Sentence', sentence, true],
    ['Remaining', remaining, true],
    ['Cell', cell || 'None', true],
    ['Jailed By', moderator || 'Unknown', true],
    ['Jailed At', jailedAt, true],
    ['Reason', reason || 'No reason provided', false],
  ]);
  return e;
}

function statusEmbed(lines, page = 1, totalPages = 1) {
  const e = base('CURRENTLY JAILED', `Showing ${lines.length} active case${lines.length === 1 ? '' : 's'}.`, COLORS.status);
  e.setDescription(lines.length ? lines.join('\n') : 'No members are currently jailed.');
  if (totalPages > 1) e.setFooter({text: `WARDEN  •  PAGE ${page}/${totalPages}`});
  return e;
}

function dashboardEmbed(stats) {
  const e = base('WARDEN DASHBOARD', null, COLORS.system);
  addFields(e, [
    ['Active Cases', stats.active, true], ['Total Cases', stats.total, true],
    ['Total Warnings', stats.warnings, true], ['Appeals Pending', stats.appeals, true],
    ['Top Moderator', stats.topModerator || '—', true], ['Most Jailed', stats.mostJailed || '—', true],
  ]);
  return e;
}

function errorEmbed(message) { return base('UNABLE TO COMPLETE REQUEST', message, COLORS.error); }
function successEmbed(title, description, fields = []) { return addFields(base(title, description, COLORS.release), fields); }
function warningEmbed(title, description, fields = []) { return addFields(base(title, description, COLORS.warning), fields); }
function systemEmbed(title, description, fields = []) { return addFields(base(title, description, COLORS.system), fields); }
function infoEmbed(title, description, fields = []) { return addFields(base(title, description, COLORS.info), fields); }

module.exports = { COLORS, base, field, addFields, jailEmbed, unjailEmbed, jailInfoEmbed, statusEmbed, dashboardEmbed, errorEmbed, successEmbed, warningEmbed, systemEmbed, infoEmbed };
