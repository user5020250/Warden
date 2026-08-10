require('dotenv').config();
const {Client, GatewayIntentBits, Collection, REST, Routes, PermissionFlagsBits} = require('discord.js');
const fs=require('fs');const path=require('path');
const client=new Client({intents:[GatewayIntentBits.Guilds,GatewayIntentBits.GuildMembers,GatewayIntentBits.GuildMessages]});
client.commands=new Collection();
const commands=[];
for(const file of fs.readdirSync(path.join(__dirname,'commands')).filter(f=>f.endsWith('.js'))){const cmd=require(`./commands/${file}`);client.commands.set(cmd.data.name,cmd);commands.push(cmd.data.toJSON())}
client.once('ready',async()=>{console.log(`Warden online as ${client.user.tag}`);const rest=new REST({version:'10'}).setToken(process.env.DISCORD_TOKEN);try{if(process.env.DEV_GUILD_ID){await rest.put(Routes.applicationGuildCommands(client.user.id,process.env.DEV_GUILD_ID),{body:commands});console.log(`Synced ${commands.length} commands to development guild.`)}else{await rest.put(Routes.applicationCommands(client.user.id),{body:commands});console.log(`Synced ${commands.length} global commands.`)}}catch(e){console.error('Command sync failed',e)}});
client.on('interactionCreate',async interaction=>{if(!interaction.isChatInputCommand())return;const cmd=client.commands.get(interaction.commandName);if(!cmd)return;try{await cmd.execute(interaction)}catch(e){console.error(e);const {errorEmbed}=require('./embeds');const payload={embeds:[errorEmbed('Something went wrong while running that command.')]};try{if(interaction.replied||interaction.deferred)await interaction.followUp(payload);else await interaction.reply({...payload,ephemeral:true})}catch{}}});
setInterval(async()=>{const {db,now,getActiveCase}=require('./db');const {releaseMember}=require('./utils');for(const c of db.prepare("SELECT * FROM jail_cases WHERE status='active' AND duration_seconds IS NOT NULL AND created_at+duration_seconds<=?").all(now())){const g=client.guilds.cache.get(String(c.guild_id));if(!g)continue;const m=await g.members.fetch(String(c.user_id)).catch(()=>null);await releaseMember(g,m,g.members.me,c.case_id,'expired').catch(()=>{});}},30000);
client.login(process.env.DISCORD_TOKEN);
