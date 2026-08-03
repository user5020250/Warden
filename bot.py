"""
Jail System Discord Bot
Entry point: loads configuration, connects to the database, loads every
cog, and starts the bot.
"""

import os
import asyncio
import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import init_db, close_db

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jailbot")

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.message_content = True  # required for the autojail spam/word filter

COGS = [
    "cogs.setup",
    "cogs.jail_basic",
    "cogs.sentence",
    "cogs.cases",
    "cogs.appeals",
    "cogs.cell",
    "cogs.mod_utils",
    "cogs.autojail",
    "cogs.statistics",
    "cogs.configuration",
    "cogs.permissions_cog",
    "cogs.logs",
    "cogs.extras",
    "cogs.scheduler",
    "cogs.help",
]


class JailBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS, help_command=None)

    async def setup_hook(self):
        await init_db()
        for cog in COGS:
            try:
                await self.load_extension(cog)
                logger.info("Loaded extension %s", cog)
            except Exception:
                logger.exception("Failed to load extension %s", cog)

        guild_id = os.getenv("DEV_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %d commands to guild %s", len(synced), guild_id)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d global commands", len(synced))

    async def close(self):
        await close_db()
        await super().close()


bot = JailBot()


@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    from utils.embeds import error_embed
    from utils.permissions import PermissionDeniedError

    if isinstance(error, PermissionDeniedError):
        message = "You do not have permission to use this command."
    elif isinstance(error, discord.app_commands.MissingPermissions):
        message = "You are missing the required Discord permission to use this command."
    elif isinstance(error, discord.app_commands.CommandOnCooldown):
        message = f"This command is on cooldown. Try again in {error.retry_after:.1f}s."
    else:
        logger.exception("Unhandled app command error", exc_info=error)
        message = "Something went wrong while running that command."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=error_embed(message), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error_embed(message), ephemeral=True)
    except discord.HTTPException:
        pass


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    bot.run(token)


if __name__ == "__main__":
    main()
