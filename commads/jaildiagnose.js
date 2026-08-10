const { SlashCommandBuilder, ChannelType } = require('discord.js');
const { systemEmbed, warningEmbed } = require('../embeds');
const { getConfig, db } = require('../db');

module.exports = {
  data: new SlashCommandBuilder().setName('jaildiagnose').setDescription('Checks Warden configuration and system health.'),
  async execute(interaction) {
    const cfg = getConfig(interaction.guild.id);
    const issues = [];
    const bot = interaction.guild.members.me || interaction.guild.members.cache.get(interaction.client.user.id);
    const role = cfg.jail_role_id ? interaction.guild.roles.cache.get(String(cfg.jail_role_id)) : null;
    const category = cfg.jail_category_id ? interaction.guild.channels.cache.get(String(cfg.jail_category_id)) : null;
    const log = cfg.log_channel_id ? interaction.guild.channels.cache.get(String(cfg.log_channel_id)) : null;

    if (!role) issues.push('Jail role is missing or not configured.');
    else if (bot && !role.editable) issues.push('Jail role is above or equal to my highest role.');
    if (!category || category.type !== ChannelType.GuildCategory) issues.push('Jail category is missing or not configured.');
    if (!log || log.type !== ChannelType.GuildText) issues.push('Log channel is missing or not configured.');
    try { db.prepare('SELECT 1').get(); } catch { issues.push('Database check failed.'); }
    if (!bot) issues.push('Bot member could not be resolved.');

    return interaction.reply({
      embeds: [issues.length
        ? warningEmbed('DIAGNOSTICS  /  ISSUES FOUND', issues.map(x => `• ${x}`).join('\n'))
        : systemEmbed('DIAGNOSTICS  /  ALL CLEAR', 'No configuration, database, role, or channel issues were detected.')],
      ephemeral: true,
    });
  },
};
