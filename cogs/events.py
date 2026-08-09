import discord
from discord.ext import commands

from database import clear_dead_cell_channel


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if isinstance(channel, discord.TextChannel):
            await clear_dead_cell_channel(channel.guild.id, channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
