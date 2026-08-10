const { SlashCommandBuilder, PermissionFlagsBits, ChannelType } = require('discord.js');
const { systemEmbed, errorEmbed } = require('../embeds');
const { getConfig, setConfig } = require('../db');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('jailsetup')
    .setDescription('Sets up the Warden jail role, category, and log channel.')
    .setDefaultMemberPermissions(PermissionFlagsBits.Administrator),

  async execute(interaction) {
    if (!interaction.memberPermissions.has(PermissionFlagsBits.Administrator)) {
      return interaction.reply({ embeds: [errorEmbed('You need Administrator permission to run this.')], ephemeral: true });
    }

    await interaction.deferReply({ ephemeral: true });
    const cfg = getConfig(interaction.guild.id);

    let role = cfg.jail_role_id ? interaction.guild.roles.cache.get(String(cfg.jail_role_id)) : null;
    if (!role) role = interaction.guild.roles.cache.find(r => r.name === 'Jailed');
    if (!role) {
      role = await interaction.guild.roles.create({ name: 'Jailed', reason: 'Warden setup' });
    }

    let category = cfg.jail_category_id ? interaction.guild.channels.cache.get(String(cfg.jail_category_id)) : null;
    if (!category) category = interaction.guild.channels.cache.find(c => c.type === ChannelType.GuildCategory && c.name.toLowerCase() === 'jail');
    if (!category) {
      category = await interaction.guild.channels.create({
        name: 'Jail',
        type: ChannelType.GuildCategory,
        permissionOverwrites: [
          { id: interaction.guild.roles.everyone.id, deny: [PermissionFlagsBits.ViewChannel] },
          { id: role.id, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory] },
        ],
        reason: 'Warden setup',
      });
    } else {
      await category.permissionOverwrites.edit(interaction.guild.roles.everyone.id, { ViewChannel: false }).catch(() => {});
      await category.permissionOverwrites.edit(role.id, { ViewChannel: true, ReadMessageHistory: true }).catch(() => {});
    }

    let log = cfg.log_channel_id ? interaction.guild.channels.cache.get(String(cfg.log_channel_id)) : null;
    if (!log) log = interaction.guild.channels.cache.find(c => c.type === ChannelType.GuildText && c.name.toLowerCase() === 'jail-logs');
    if (!log) {
      log = await interaction.guild.channels.create({
        name: 'jail-logs',
        type: ChannelType.GuildText,
        permissionOverwrites: [{ id: interaction.guild.roles.everyone.id, deny: [PermissionFlagsBits.ViewChannel] }],
        reason: 'Warden setup',
      });
    }

    setConfig(interaction.guild.id, {
      jail_role_id: role.id,
      jail_category_id: category.id,
      log_channel_id: log.id,
    });

    return interaction.editReply({
      embeds: [systemEmbed('WARDEN SETUP COMPLETE', 'The core jail system is configured.', [
        ['Jail Role', role.toString(), true],
        ['Jail Category', `\`${category.name}\``, true],
        ['Log Channel', log.toString(), true],
      ])],
    });
  },
};
