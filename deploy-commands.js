require('dotenv').config();
const {REST,Routes}=require('discord.js');const fs=require('fs');const path=require('path');
const commands=fs.readdirSync(path.join(__dirname,'commands')).filter(f=>f.endsWith('.js')).map(f=>require(`./commands/${f}`).data.toJSON());
const rest=new REST({version:'10'}).setToken(process.env.DISCORD_TOKEN);
(async()=>{const route=process.env.DEV_GUILD_ID?Routes.applicationGuildCommands(process.env.CLIENT_ID,process.env.DEV_GUILD_ID):Routes.applicationCommands(process.env.CLIENT_ID);await rest.put(route,{body:commands});console.log(`Registered ${commands.length} commands.`)})().catch(console.error);
