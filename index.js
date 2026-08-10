require('dotenv').config();
const fs = require('fs');
const path = require('path');
const {
  Client,
  Collection,
  GatewayIntentBits,
  REST,
  Routes,
} = require('discord.js');
const { db, now, getActiveCase } = require('./db');
const { releaseMember, expireVisitations } = require('./utils');

if (!process.env.DISCORD_TOKEN) {
  console.error('Missing DISCORD_TOKEN environment variable.');
  process.exit(1);
}

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMembers],
});

client.commands = new Collection();
const commandsPath = path.join(__dirname, 'commands');
const commandFiles = fs.readdirSync(commandsPath).filter(file => file.endsWith('.js'));
const commandData = [];

for (const file of commandFiles) {
  const command = require(path.join(commandsPath, file));
  if (!command?.data?.name || typeof command.execute !== 'function') {
    console.warn(`Skipping invalid command file: ${file}`);
    continue;
  }
  client.commands.set(command.data.name, command);
  commandData.push(command.data.toJSON());
}

async function syncCommands() {
  const clientId = process.env.CLIENT_ID || client.user.id;
  const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);

  if (process.env.DEV_GUILD_ID) {
    await rest.put(
      Routes.applicationGuildCommands(clientId, process.env.DEV_GUILD_ID),
      { body: commandData },
    );
    console.log(`Synced ${commandData.length} commands to development guild ${process.env.DEV_GUILD_ID}.`);
  } else {
    await rest.put(
      Routes.applicationCommands(clientId),
      { body: commandData },
    );
    console.log(`Synced ${commandData.length} global commands.`);
  }
}

client.once('ready', async () => {
  console.log(`Warden online as ${client.user.tag}`);
  console.log(`Loaded ${client.commands.size} commands.`);

  try {
    await syncCommands();
  } catch (error) {
    console.error('Command sync failed:', error);
  }

  setInterval(async () => {
    try {
      const expired = db.prepare(`
        SELECT * FROM jail_cases
        WHERE status = 'active'
          AND duration_seconds IS NOT NULL
          AND created_at + duration_seconds <= ?
      `).all(now());

      for (const jailCase of expired) {
        const guild = client.guilds.cache.get(String(jailCase.guild_id));
        if (!guild) continue;

        const member = await guild.members.fetch(String(jailCase.user_id)).catch(() => null);
        const botMember = guild.members.me;
        const result = await releaseMember(
          guild,
          member,
          botMember,
          jailCase.case_id,
          'expired',
        ).catch(error => ({ ok: false, message: error.message }));

        if (result.ok) {
          console.log(`Expired case #${jailCase.case_id} in guild ${guild.id}.`);
        } else {
          console.error(`Could not expire case #${jailCase.case_id}: ${result.message}`);
        }
      }

      await expireVisitations(client);
    } catch (error) {
      console.error('Warden scheduler error:', error);
    }
  }, 30_000);
});

client.on('interactionCreate', async interaction => {
  if (!interaction.isChatInputCommand()) return;

  const command = client.commands.get(interaction.commandName);
  if (!command) return;

  try {
    await command.execute(interaction);
  } catch (error) {
    console.error(`Command /${interaction.commandName} failed:`, error);
    const { errorEmbed } = require('./embeds');
    const payload = {
      embeds: [errorEmbed('Something went wrong while running that command. Check the bot logs for details.')],
      ephemeral: true,
    };

    try {
      if (interaction.replied || interaction.deferred) await interaction.followUp(payload);
      else await interaction.reply(payload);
    } catch {}
  }
});

process.on('SIGTERM', () => {
  try { db.close(); } catch {}
  client.destroy();
});

process.on('SIGINT', () => {
  try { db.close(); } catch {}
  client.destroy();
});

client.login(process.env.DISCORD_TOKEN);
