require('dotenv').config();
const fs = require('fs');
const path = require('path');
const { REST, Routes } = require('discord.js');

if (!process.env.DISCORD_TOKEN) throw new Error('Missing DISCORD_TOKEN.');
if (!process.env.CLIENT_ID) throw new Error('Missing CLIENT_ID.');

const commandsDir = path.join(__dirname, 'commands');
const commands = fs.readdirSync(commandsDir)
  .filter(file => file.endsWith('.js'))
  .map(file => require(path.join(commandsDir, file)).data.toJSON());

const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
const route = process.env.DEV_GUILD_ID
  ? Routes.applicationGuildCommands(process.env.CLIENT_ID, process.env.DEV_GUILD_ID)
  : Routes.applicationCommands(process.env.CLIENT_ID);

(async () => {
  await rest.put(route, { body: commands });
  console.log(`Registered ${commands.length} commands.`);
})().catch(error => {
  console.error('Command registration failed:', error);
  process.exit(1);
});
