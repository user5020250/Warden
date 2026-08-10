const { SlashCommandBuilder } = require('discord.js');
const { errorEmbed, successEmbed, warningEmbed, infoEmbed } = require('../embeds');
const { db, now, getCase, getActiveCase } = require('../db');
const { requireStaff, releaseMember, notifyAndLog } = require('../utils');

const data = new SlashCommandBuilder()
  .setName('appeal')
  .setDescription('Submit or manage jail appeals.')
  .addSubcommand(s => s.setName('create').setDescription('Submit an appeal for your case.').addIntegerOption(o => o.setName('case_id').setDescription('Case ID').setRequired(true)).addStringOption(o => o.setName('reason').setDescription('Appeal reason').setRequired(true)))
  .addSubcommand(s => s.setName('view').setDescription('View an appeal.').addIntegerOption(o => o.setName('appeal_id').setDescription('Appeal ID').setRequired(true)))
  .addSubcommand(s => s.setName('approve').setDescription('Approve an appeal and release the active case.').addIntegerOption(o => o.setName('appeal_id').setDescription('Appeal ID').setRequired(true)).addStringOption(o => o.setName('reason').setDescription('Decision reason')))
  .addSubcommand(s => s.setName('deny').setDescription('Deny an appeal.').addIntegerOption(o => o.setName('appeal_id').setDescription('Appeal ID').setRequired(true)).addStringOption(o => o.setName('reason').setDescription('Decision reason')))
  .addSubcommand(s => s.setName('cancel').setDescription('Cancel your pending appeal.').addIntegerOption(o => o.setName('appeal_id').setDescription('Appeal ID').setRequired(true)));

module.exports = {
  data,
  async execute(interaction) {
    const guildId = String(interaction.guild.id);
    const sub = interaction.options.getSubcommand();

    if (sub === 'create') {
      const caseId = interaction.options.getInteger('case_id');
      const jailCase = getCase(guildId, caseId);
      if (!jailCase || String(jailCase.user_id) !== String(interaction.user.id)) {
        return interaction.reply({ embeds: [errorEmbed('You can only appeal your own jail case.')], ephemeral: true });
      }

      const existing = db.prepare("SELECT * FROM appeals WHERE guild_id = ? AND case_id = ? AND user_id = ? AND status = 'pending'").get(guildId, caseId, String(interaction.user.id));
      if (existing) return interaction.reply({ embeds: [errorEmbed(`You already have pending appeal #${existing.appeal_id} for case #${caseId}.`)], ephemeral: true });

      const reason = interaction.options.getString('reason');
      const result = db.prepare('INSERT INTO appeals(guild_id, case_id, user_id, reason, created_at) VALUES (?, ?, ?, ?, ?)')
        .run(guildId, caseId, String(interaction.user.id), reason, now());

      return interaction.reply({
        embeds: [successEmbed('APPEAL SUBMITTED', `Your appeal for case \`#${caseId}\` has been submitted.`, [
          ['Appeal ID', `#${result.lastInsertRowid}`, true],
          ['Status', 'PENDING', true],
        ])],
        ephemeral: true,
      });
    }

    if (sub === 'cancel') {
      const appealId = interaction.options.getInteger('appeal_id');
      const appeal = db.prepare('SELECT * FROM appeals WHERE guild_id = ? AND appeal_id = ?').get(guildId, appealId);
      if (!appeal) return interaction.reply({ embeds: [errorEmbed(`Appeal #${appealId} could not be found.`)], ephemeral: true });
      if (String(appeal.user_id) !== String(interaction.user.id) && !(await requireStaff(interaction))) return;
      if (appeal.status !== 'pending') return interaction.reply({ embeds: [errorEmbed(`Appeal #${appealId} is already ${appeal.status}.`)], ephemeral: true });

      db.prepare('UPDATE appeals SET status = \'cancelled\', decided_by = ?, decided_at = ? WHERE guild_id = ? AND appeal_id = ?')
        .run(String(interaction.user.id), now(), guildId, appealId);
      return interaction.reply({ embeds: [successEmbed('APPEAL CANCELLED', `Appeal #${appealId} has been cancelled.`)] });
    }

    if (!(await requireStaff(interaction))) return;

    const appealId = interaction.options.getInteger('appeal_id');
    const appeal = db.prepare('SELECT * FROM appeals WHERE guild_id = ? AND appeal_id = ?').get(guildId, appealId);
    if (!appeal) return interaction.reply({ embeds: [errorEmbed(`Appeal #${appealId} could not be found.`)], ephemeral: true });

    if (sub === 'view') {
      return interaction.reply({ embeds: [infoEmbed(`APPEAL #${appealId}`, null, [
        ['Appellant', `<@${appeal.user_id}>`, true],
        ['Case ID', `#${appeal.case_id}`, true],
        ['Status', appeal.status.toUpperCase(), true],
        ['Submitted', `<t:${appeal.created_at}:F>`, true],
        ['Reason', appeal.reason, false],
        ['Decision', appeal.decision_reason || '—', false],
      ])] });
    }

    if (appeal.status !== 'pending') return interaction.reply({ embeds: [errorEmbed(`Appeal #${appealId} is already ${appeal.status}.`)], ephemeral: true });

    const decisionReason = interaction.options.getString('reason') || null;

    if (sub === 'approve') {
      const member = await interaction.guild.members.fetch(String(appeal.user_id)).catch(() => null);
      const activeCase = getActiveCase(guildId, appeal.user_id);
      if (activeCase) {
        const result = await releaseMember(interaction.guild, member, interaction.member, activeCase.case_id, 'pardoned');
        if (!result.ok) return interaction.reply({ embeds: [errorEmbed(result.message)], ephemeral: true });
        await notifyAndLog(interaction.guild, {
          action: 'appeal_approved',
          userId: appeal.user_id,
          moderatorId: interaction.user.id,
          caseId: activeCase.case_id,
          detail: decisionReason || 'Appeal approved',
          dmTarget: member?.user,
          dmEmbed: successEmbed('APPEAL APPROVED', `Your appeal for case #${activeCase.case_id} was approved. You have been released.`),
          logEmbed: successEmbed('APPEAL APPROVED', `${member || `<@${appeal.user_id}>`} was released after appeal #${appealId} was approved.`, [
            ['Case ID', `#${activeCase.case_id}`, true],
            ['Moderator', interaction.member.toString(), true],
            ['Reason', decisionReason || 'No decision reason provided', false],
          ]),
        });
      }

      db.prepare('UPDATE appeals SET status = \'approved\', decided_by = ?, decided_at = ?, decision_reason = ? WHERE guild_id = ? AND appeal_id = ?')
        .run(String(interaction.user.id), now(), decisionReason, guildId, appealId);
      return interaction.reply({ embeds: [successEmbed('APPEAL APPROVED', `Appeal #${appealId} has been approved.`)] });
    }

    db.prepare('UPDATE appeals SET status = \'denied\', decided_by = ?, decided_at = ?, decision_reason = ? WHERE guild_id = ? AND appeal_id = ?')
      .run(String(interaction.user.id), now(), decisionReason, guildId, appealId);
    return interaction.reply({ embeds: [warningEmbed('APPEAL DENIED', `Appeal #${appealId} has been denied.`, [['Reason', decisionReason || 'No reason provided', false]])] });
  },
};
