const { SlashCommandBuilder, ActionRowBuilder, StringSelectMenuBuilder } = require('discord.js');
const { infoEmbed } = require('../embeds');

const categories = {
  Jail: [
    '`/jail <member> [duration] [reason]` — Jail a member.',
    '`/unjail <member>` — Release a jailed member.',
    '`/jailstatus` — List active jail cases.',
    '`/jailinfo <member>` — View current jail information.',
  ],
  Sentence: [
    '`/sentence view <member>` — View remaining time.',
    '`/sentence set <member> <duration>` — Set a sentence.',
    '`/sentence extend <member> <duration>` — Add time.',
    '`/sentence reduce <member> <duration>` — Remove time.',
    '`/sentence end <member>` — End and release.',
  ],
  Cases: [
    '`/case view` — View your recorded cases.',
    '`/case notes <case_id> <note>` — Add a moderator note.',
    '`/case evidence <case_id> <url>` — Attach evidence.',
    '`/caseinfo <case_id>` — View a case.',
    '`/jailhistory <member>` — View jail history.',
    '`/jailsearch <query>` — Search cases.',
    '`/jaillogs` — View recent actions.',
  ],
  Warnings: [
    '`/warn <member> <reason>` — Issue a warning.',
    '`/warnings list <member>` — List warnings.',
    '`/warnings info <warning_id>` — View a warning.',
    '`/warnings delete <warning_id>` — Delete a warning.',
    '`/warnings clear <member>` — Clear warnings.',
  ],
  Reports: [
    '`/report <member> <reason> [evidence]` — Submit a report.',
    '`/reports` — View reports.',
    '`/reportinfo <report_id>` — View a report.',
    '`/reportclose <report_id> [reason]` — Close a report.',
  ],
  Appeals: [
    '`/appeal create <case_id> <reason>` — Submit an appeal.',
    '`/appeal view <appeal_id>` — View an appeal.',
    '`/appeal approve <appeal_id>` — Approve and release an active case.',
    '`/appeal deny <appeal_id> [reason]` — Deny an appeal.',
    '`/appeal cancel <appeal_id>` — Cancel an appeal.',
    '`/appeals` — List pending appeals.',
  ],
  Cells: [
    '`/cell visit <member> <visitor> <duration>` — Grant temporary access.',
    '`/cellmate list <member>` — List cellmates.',
    '`/cellmate add <member> <cellmate>` — Add a cellmate.',
    '`/cellmate remove <member> <cellmate>` — Remove a cellmate.',
  ],
  Statistics: [
    '`/jailstats overview` — Overview.',
    '`/jailstats top` — Most jailed members.',
    '`/jailstats moderators` — Most active moderators.',
    '`/jailstats activity` — Recent activity.',
    '`/jailstats longest` — Longest sentences.',
    '`/jailstats oldest` — Oldest active cases.',
  ],
  System: [
    '`/jailsetup` — Create the core jail configuration.',
    '`/jailconfig` — Configure Warden.',
    '`/jaildiagnose` — Check system health.',
    '`/help` — Open this panel.',
  ],
};

module.exports = {
  data: new SlashCommandBuilder().setName('help').setDescription('Shows Warden commands by category.'),

  async execute(interaction) {
    const menu = new StringSelectMenuBuilder()
      .setCustomId(`warden-help:${interaction.user.id}`)
      .setPlaceholder('Select a category')
      .addOptions(Object.keys(categories).map(category => ({
        label: category,
        value: category,
        description: `View ${category.toLowerCase()} commands.`,
      })));

    const row = new ActionRowBuilder().addComponents(menu);
    await interaction.reply({ embeds: [infoEmbed('WARDEN HELP', 'Select a category below to view available commands.')], components: [row] });

    const message = await interaction.fetchReply();
    const collector = message.createMessageComponentCollector({
      filter: component => component.customId === `warden-help:${interaction.user.id}`,
      time: 180000,
    });

    collector.on('collect', async component => {
      const category = component.values[0];
      await component.update({
        embeds: [infoEmbed(`WARDEN HELP  /  ${category.toUpperCase()}`, categories[category].join('\n'))],
        components: [row],
      });
    });
  },
};
