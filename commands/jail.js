const {SlashCommandBuilder,PermissionFlagsBits}=require('discord.js');
const {errorEmbed,jailEmbed,unjailEmbed,statusEmbed,jailInfoEmbed}=require('../embeds');
const {getActiveCase,getConfig,db,now}=require('../db');
const {requireStaff,parseDuration,formatDuration,remaining,jailMember,releaseMember,notifyAndLog}=require('../utils');
module.exports={
 data:new SlashCommandBuilder().setName('jail').setDescription('Jails a member and opens a case.')
  .addUserOption(o=>o.setName('member').setDescription('The member to jail').setRequired(true))
  .addStringOption(o=>o.setName('duration').setDescription('30m, 2h, 1d, or permanent'))
  .addStringOption(o=>o.setName('reason').setDescription('Why this member is being jailed')),
 async execute(i){if(!(await requireStaff(i)))return;const m=await i.guild.members.fetch(i.options.getUser('member').id);if(m.id===i.user.id)return i.reply({embeds:[errorEmbed('You cannot jail yourself.')],ephemeral:true});if(m.user.bot)return i.reply({embeds:[errorEmbed('You cannot jail a bot.')],ephemeral:true});if(m.id===i.guild.ownerId)return i.reply({embeds:[errorEmbed('You cannot jail the server owner.')],ephemeral:true});const existing=getActiveCase(i.guild.id,m.id);if(existing)return i.reply({embeds:[errorEmbed(`${m} is already jailed under case \`#${existing.case_id}\`.`)],ephemeral:true});const cfg=getConfig(i.guild.id);let seconds;try{seconds=i.options.getString('duration')?parseDuration(i.options.getString('duration')):cfg.default_seconds}catch(e){return i.reply({embeds:[errorEmbed(e.message)],ephemeral:true})}const reason=i.options.getString('reason');await i.deferReply();const result=await jailMember(i.guild,m,i.member,reason,seconds);if(!result.ok)return i.editReply({embeds:[errorEmbed(result.message)]});const cell=result.cell?result.cell.toString():'None';const embed=jailEmbed({member:m.toString(),caseId:result.caseId,duration:formatDuration(seconds),reason,moderator:i.member.toString(),cell});await notifyAndLog(i.guild,{action:'jail',userId:m.id,moderatorId:i.user.id,caseId:result.caseId,detail:reason,dmTarget:m.user,dmEmbed:embed,logEmbed:embed});return i.editReply({embeds:[embed]});}
};
