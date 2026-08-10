const { SlashCommandBuilder, PermissionFlagsBits } = require('discord.js');
const { errorEmbed, successEmbed, infoEmbed } = require('../embeds');
const { db, now, getActiveCase } = require('../db');
const { requireStaff } = require('../utils');

const data = new SlashCommandBuilder()
  .setName('cellmate')
  .setDescription('Manage shared jail cells.')
  .addSubcommand(s => s.setName('list').setDescription('List cellmates.').addUserOption(o => o.setName('member').setDescription('Current occupant').setRequired(true)))
  .addSubcommand(s => s.setName('add').setDescription('Add a cellmate.').addUserOption(o => o.setName('member').setDescription('Current occupant').setRequired(true)).addUserOption(o => o.setName('cellmate').setDescription('Member to add').setRequired(true)))
  .addSubcommand(s => s.setName('remove').setDescription('Remove a cellmate.').addUserOption(o => o.setName('member').setDescription('Current occupant').setRequired(true)).addUserOption(o => o.setName('cellmate').setDescription('Cellmate').setRequired(true)));

module.exports = {
  data,
  async execute(interaction) {
    if (!(await requireStaff(interaction))) return;
    const sub = interaction.options.getSubcommand();
    const occupant = interaction.options.getUser('member');
    const currentCase = getActiveCase(interaction.guild.id, occupant.id);
    if (!currentCase || !currentCase.cell_channel_id) return interaction.reply({ embeds: [errorEmbed(`${occupant} does not have an active cell.`)], ephemeral: true });

    const channel = interaction.guild.channels.cache.get(String(currentCase.cell_channel_id));
    if (!channel) return interaction.reply({ embeds: [errorEmbed('The cell channel no longer exists.')], ephemeral: true });

    if (sub === 'list') {
      const rows = db.prepare('SELECT * FROM cellmates WHERE guild_id = ? AND case_id = ? ORDER BY created_at ASC').all(String(interaction.guild.id), currentCase.case_id);
      return interaction.reply({ embeds: [infoEmbed('CELLMATES', rows.length ? rows.map(row => `<@${row.member_id}>`).join('\n') : 'No cellmates assigned.')] });
    }

    const cellmate = interaction.options.getUser('cellmate');
    if (cellmate.id === occupant.id) return interaction.reply({ embeds: [errorEmbed('The occupant cannot be their own cellmate.')], ephemeral: true });

    const member = await interaction.guild.members.fetch(cellmate.id).catch(() => null);
    if (!member) return interaction.reply({ embeds: [errorEmbed('That member is not in this server.')], ephemeral: true });

    if (sub === 'add') {
      db.prepare('INSERT OR IGNORE INTO cellmates(guild_id, case_id, member_id, added_by, created_at) VALUES (?, ?, ?, ?, ?)')
        .run(String(interaction.guild.id), currentCase.case_id, String(cellmate.id), String(interaction.user.id), now());
      await channel.permissionOverwrites.edit(cellmate.id, {
        ViewChannel: true,
        SendMessages: true,
        ReadMessageHistory: true,
      }).catch(() => {});
      return interaction.reply({ embeds: [successEmbed('CELLMATE ADDED', `${cellmate} has been added to ${channel}.`)] });
    }

    db.prepare('DELETE FROM cellmates WHERE guild_id = ? AND case_id = ? AND member_id = ?')
      .run(String(interaction.guild.id), currentCase.case_id, String(cellmate.id));
    await channel.permissionOverwrites.delete(cellmate.id, 'Warden cellmate removed').catch(() => {});
    return interaction.reply({ embeds: [successEmbed('CELLMATE REMOVED', `${cellmate} has been removed from ${channel}.`)] });
  },
};
