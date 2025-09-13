# cogs/birthdays.py
import discord
from discord import app_commands
from discord.ext import commands
from database import get_birthdays, get_guild_config
from utils import format_birthday_display, update_pinned_birthday_message
from datetime import datetime, timezone

ENTRIES_PER_PAGE = 20
CONFETTI_ICON = "🎉"

class Birthdays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="birthdaylist",
        description="View the full birthday list with pagination."
    )
    async def birthdaylist(self, interaction: discord.Interaction):
        guild = interaction.guild
        guild_id = str(guild.id)

        # Fetch birthdays
        birthdays = await get_birthdays(guild_id)
        if not birthdays:
            await interaction.response.send_message("📂 No birthdays found yet.", ephemeral=True)
            return

        # Sort by upcoming date
        today = datetime.now(timezone.utc)
        today_month, today_day = today.month, today.day

        def upcoming_sort_key(bday_tuple):
            month, day = map(int, bday_tuple[1].split("-"))
            # Feb 29 handling
            if month == 2 and day == 29:
                is_leap = (today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0))
                if not is_leap:
                    day = 28
            delta = (month - today_month) * 31 + (day - today_day)
            return delta if delta >= 0 else delta + 12 * 31

        sorted_birthdays = sorted(birthdays, key=upcoming_sort_key)

        # Highlight today's birthdays
        today_ids = [
            uid for uid, bday in sorted_birthdays
            if int(bday.split("-")[0]) == today_month and int(bday.split("-")[1]) == today_day
        ]

        # Update pinned message first
        try:
            await update_pinned_birthday_message(guild, highlight_today=today_ids, manual=True)
        except Exception as e:
            print(f"[WARN] Could not update pinned birthday message: {e}")

        # Split into pages
        pages = []
        for i in range(0, len(sorted_birthdays), ENTRIES_PER_PAGE):
            chunk = sorted_birthdays[i:i + ENTRIES_PER_PAGE]
            lines = []
            for uid, bday in chunk:
                member = guild.get_member(int(uid))
                name = member.display_name if member else f"<@{uid}>"
                if uid in today_ids:
                    name = f"{CONFETTI_ICON} {name}"
                lines.append(f"✦ {name}: {format_birthday_display(bday)}")
            content = "\n".join(lines)
            pages.append(content)

        # Pagination View
        class BirthdayView(discord.ui.View):
            def __init__(self, total_pages):
                super().__init__(timeout=180)
                self.page = 0
                self.total_pages = total_pages
                # Disable buttons if only 1 page
                if total_pages <= 1:
                    for child in self.children:
                        child.disabled = True

            async def update_embed(self, interaction_button: discord.Interaction):
                embed = discord.Embed(
                    title=f"🎂 Birthday List (Page {self.page+1}/{self.total_pages})",
                    description=pages[self.page]
                )
                embed.set_footer(text="Pinned message updated automatically. Use /birthdaylist anytime!")
                await interaction_button.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.blurple)
            async def prev_page(self, interaction_button: discord.Interaction, button: discord.ui.Button):
                if self.page > 0:
                    self.page -= 1
                    await self.update_embed(interaction_button)

            @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.blurple)
            async def next_page(self, interaction_button: discord.Interaction, button: discord.ui.Button):
                if self.page < self.total_pages - 1:
                    self.page += 1
                    await self.update_embed(interaction_button)

        view = BirthdayView(total_pages=len(pages))
        embed = discord.Embed(
            title=f"🎂 Birthday List (Page 1/{len(pages)})",
            description=pages[0]
        )
        embed.set_footer(text="Pinned message updated automatically. Use /birthdaylist anytime!")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
