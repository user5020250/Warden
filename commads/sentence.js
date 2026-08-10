const { SlashCommandBuilder } = require('discord.js');
const { errorEmbed, successEmbed } = require('../embeds');
const { getActiveCase, db, now } = require('../db');
const { requireStaff, parseDuration, formatDuration, remaining, releaseMember } = require('../utils');

const data = new SlashCommandBuilder()
  .setName('sentence')
  .setDescription('View or change an active jail sentence.')
  .addSubcommand(s => s.setName('view').setDescription('View a member sentence.').addUserOption(o => o.setName('member').setDescription('Member').setRequired(true)))
  .addSubcommand(s => s.setName('set').setDescription('Set a sentence.').addUserOption(o => o.setName('member').setDescription('Member').setRequired(true)).addStringOption(o => o.setName('duration').setDescription('Duration').setRequired(true)))
  .addSubcommand(s => s.setName('extend').setDescription('Extend a sentence.').addUserOption(o => o.setName('member').setDescription('Member').setRequired(true)).addStringOption(o => o.setName('duration').setDescription('Duration').setRequired(true)))
  .addSubcommand(s => s.setName('reduce').setDescription('Reduce a sentence.').addUserOption(o => o.setName('member').setDescription('Member').setRequired(true)).addStringOption(o => o.setName('duration').setDescription('Duration').setRequired(true)))
  .addSubcommand(s => s.setName('end').setDescription('End a sentence and release the member.').addUserOption(o => o.setName('member').setDescription('Member').setRequired(true)));

module.exports = {
  data,
  async execute(interaction) {
    if (!(await requireStaff(interaction))) return;

    const sub = interaction.options.getSubcommand();
    const user = interaction.options.getUser('member');
    const member = await interaction.guild.members.fetch(user.id);
    const currentCase = getActiveCase(interaction.guild.id, member.id);

    if (!currentCase) return interaction.reply({ embeds: [errorEmbed(`${member} is not currently jailed.`)], ephemeral: true });

    if (sub === 'view') {
      return interaction.reply({
        embeds: [successEmbed('SENTENCE INFORMATION', `${member}`, [
          ['Remaining', currentCase.duration_seconds == null ? 'Permanent' : formatDuration(remaining(currentCase)), true],
          ['Case', `#${currentCase.case_id}`, true],
          ['Original Duration', currentCase.duration_seconds == null ? 'Permanent' : formatDuration(currentCase.duration_seconds), true],
        ])],
      });
    }

    if (sub === 'end') {
      const result = await releaseMember(interaction.guild, member, interaction.member, currentCase.case_id, 'released');
      if (!result.ok) return interaction.reply({ embeds: [errorEmbed(result.message)], ephemeral: true });
      return interaction.reply({ embeds: [successEmbed('SENTENCE ENDED', `${member} has been released from case \`#${currentCase.case_id}\`.`)] });
    }

    const rawDuration = interaction.options.getString('duration');
    let requested;
    try {
      requested = parseDuration(rawDuration);
    } catch (error) {
      return interaction.reply({ embeds: [errorEmbed(error.message)], ephemeral: true });
    }

    let newDuration;
    if (sub === 'set') {
      newDuration = requested;
    } else {
      if (requested == null) return interaction.reply({ embeds: [errorEmbed('`permanent` can only be used with `/sentence set`.')], ephemeral: true });
      const currentRemaining = remaining(currentCase) ?? 0;
      newDuration = sub === 'extend' ? currentRemaining + requested : Math.max(0, currentRemaining - requested);
    }

    if (newDuration === 0) {
      const result = await releaseMember(interaction.guild, member, interaction.member, currentCase.case_id, 'released');
      if (!result.ok) return interaction.reply({ embeds: [errorEmbed(result.message)], ephemeral: true });
      return interaction.reply({ embeds: [successEmbed('SENTENCE ENDED', `${member} has been released because the sentence reached zero.`)] });
    }

    db.prepare('UPDATE jail_cases SET created_at = ?, duration_seconds = ? WHERE guild_id = ? AND case_id = ? AND status = \'active\'')
      .run(now(), newDuration, String(interaction.guild.id), currentCase.case_id);

    return interaction.reply({
      embeds: [successEmbed(
        sub === 'set' ? 'SENTENCE UPDATED' : sub === 'extend' ? 'SENTENCE EXTENDED' : 'SENTENCE REDUCED',
        `Case \`#${currentCase.case_id}\` for ${member} now has **${formatDuration(newDuration)}** remaining.`,
      )],
    });
  },
};
