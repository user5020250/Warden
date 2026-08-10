const { SlashCommandBuilder } = require('discord.js');
const { dashboardEmbed, infoEmbed } = require('../embeds');
const { db } = require('../db');
const { requireStaff, formatDuration } = require('../utils');

const data = new SlashCommandBuilder()
  .setName('jailstats')
  .setDescription('Warden statistics.')
  .addSubcommand(s => s.setName('overview').setDescription('Overview statistics.'))
  .addSubcommand(s => s.setName('top').setDescription('Most frequently jailed members.'))
  .addSubcommand(s => s.setName('moderators').setDescription('Most active moderators.'))
  .addSubcommand(s => s.setName('activity').setDescription('Recent activity.'))
  .addSubcommand(s => s.setName('longest').setDescription('Longest sentences.'))
  .addSubcommand(s => s.setName('oldest').setDescription('Oldest active cases.'));

module.exports = {
  data,
  async execute(interaction) {
    if (!(await requireStaff(interaction))) return;
    const guildId = String(interaction.guild.id);
    const sub = interaction.options.getSubcommand();

    if (sub === 'overview') {
      const active = db.prepare("SELECT COUNT(*) AS n FROM jail_cases WHERE guild_id = ? AND status = 'active'").get(guildId).n;
      const total = db.prepare('SELECT COUNT(*) AS n FROM jail_cases WHERE guild_id = ?').get(guildId).n;
      const warnings = db.prepare('SELECT COUNT(*) AS n FROM warnings WHERE guild_id = ?').get(guildId).n;
      const appeals = db.prepare("SELECT COUNT(*) AS n FROM appeals WHERE guild_id = ? AND status = 'pending'").get(guildId).n;
      const topModerator = db.prepare('SELECT moderator_id, COUNT(*) AS n FROM jail_cases WHERE guild_id = ? GROUP BY moderator_id ORDER BY n DESC LIMIT 1').get(guildId);
      const mostJailed = db.prepare('SELECT user_id, COUNT(*) AS n FROM jail_cases WHERE guild_id = ? GROUP BY user_id ORDER BY n DESC LIMIT 1').get(guildId);

      return interaction.reply({ embeds: [dashboardEmbed({
        active,
        total,
        warnings,
        appeals,
        topModerator: topModerator ? `<@${topModerator.moderator_id}> — ${topModerator.n} cases` : '—',
        mostJailed: mostJailed ? `<@${mostJailed.user_id}> — ${mostJailed.n} cases` : '—',
      })] });
    }

    let title;
    let rows;
    if (sub === 'top') {
      title = 'TOP JAILED MEMBERS';
      rows = db.prepare('SELECT user_id, COUNT(*) AS n FROM jail_cases WHERE guild_id = ? GROUP BY user_id ORDER BY n DESC LIMIT 10').all(guildId);
      rows = rows.map((r, index) => `**${index + 1}.** <@${r.user_id}> — ${r.n} cases`);
    } else if (sub === 'moderators') {
      title = 'TOP MODERATORS';
      rows = db.prepare('SELECT moderator_id, COUNT(*) AS n FROM jail_cases WHERE guild_id = ? GROUP BY moderator_id ORDER BY n DESC LIMIT 10').all(guildId);
      rows = rows.map((r, index) => `**${index + 1}.** <@${r.moderator_id}> — ${r.n} cases`);
    } else if (sub === 'activity') {
      title = 'RECENT ACTIVITY';
      rows = db.prepare('SELECT * FROM action_logs WHERE guild_id = ? ORDER BY created_at DESC LIMIT 10').all(guildId);
      rows = rows.map(r => `**${r.action.toUpperCase()}** — <t:${r.created_at}:R> — Case ${r.case_id ? `#${r.case_id}` : '—'}`);
    } else if (sub === 'longest') {
      title = 'LONGEST SENTENCES';
      rows = db.prepare('SELECT * FROM jail_cases WHERE guild_id = ? AND duration_seconds IS NOT NULL ORDER BY duration_seconds DESC LIMIT 10').all(guildId);
      rows = rows.map(r => `**#${r.case_id}** — <@${r.user_id}> — ${formatDuration(r.duration_seconds)} — ${r.status.toUpperCase()}`);
    } else {
      title = 'OLDEST ACTIVE CASES';
      rows = db.prepare("SELECT * FROM jail_cases WHERE guild_id = ? AND status = 'active' ORDER BY created_at ASC LIMIT 10").all(guildId);
      rows = rows.map(r => `**#${r.case_id}** — <@${r.user_id}> — <t:${r.created_at}:R>`);
    }

    return interaction.reply({ embeds: [infoEmbed(title, rows.length ? rows.join('\n') : 'No data available.')] });
  },
};
