"""
Generic Previous/Next/Close paginator. Every command that lists more than
a handful of rows (jailstatus, reports, warnings list, appeals, jailhistory,
jailsearch, jaillogs) renders through this so paging behaves identically
everywhere.
"""

import discord

from config import PAGE_SIZE
from utils.embeds import build_embed


class Paginator(discord.ui.View):
    def __init__(self, title: str, lines: list[str], empty_message: str, page_size: int = PAGE_SIZE):
        super().__init__(timeout=180)
        self.title = title
        self.lines = lines
        self.empty_message = empty_message
        self.page_size = page_size
        self.page = 0
        self.max_page = max(0, (len(lines) - 1) // page_size)
        self._update_buttons()

    def _update_buttons(self):
        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= self.max_page

    def render(self) -> discord.Embed:
        if not self.lines:
            return build_embed(self.title, self.empty_message)
        start = self.page * self.page_size
        chunk = self.lines[start:start + self.page_size]
        title = self.title if self.max_page == 0 else f"{self.title} (Page {self.page + 1}/{self.max_page + 1})"
        return build_embed(title, "\n".join(chunk))

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.max_page, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()
        self.stop()
