import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from database import set_birthday, delete_birthday, get_guild_config, get_birthdays
from utils import parse_day_month_input, format_birthday_display, is_birthday_on_date
from logger import logger
import datetime as dt

CONFETTI_ICON = "🎉"
ENTRIES_PER_PAGE = 20

# ----------------- Setup Check -----------------
async def ensure_setup(interaction: discord.Interaction) -> bool:
    guild_config = await get_guild_config(str(interaction.guild.id))
    if not guild_config:
        await interaction.response.send_message(
            "❗ Please run `/setup` first to configure HWB-BirthdayHelper for this server!",
            ephemeral=True
        )
        return False
    return True

# ---------------- Pagination -----------------
def paginate_birthdays(birthdays: list[tuple[str, str]], per_page: int = ENTRIES_PER_PAGE):
    return [birthdays[i:i + per_page] for i in range(0, len(birthdays), per_page)]

def format_birthday_page(page: list[tuple[str, str]], guild: discord.Guild, test_mode: bool = False):
    today = dt.datetime.now(dt.timezone.utc)
    lines = []
    for user_id, birthday in page:
        if test_mode:
            name = f"User{int(user_id[-3:]):03d}"
        else:
            member = guild.get_member(int(user_id))
            name = member.display_name if member else f"<@{user_id}>"
        prefix = CONFETTI_ICON + " " if is_birthday_on_date(birthday, today) else "・"
        lines.append(f"{prefix}{name} - {format_birthday_display(birthday)}")
    return "\n".join(lines)

# ---------------- Pagination View -----------------
class BirthdayPages(View):
    def __init__(self, pages: list[str], message: discord.Message, guild: discord.Guild):
        super().__init__(timeout=None)  # infinite timeout
        self.pages = pages
        self.message = message
        self.guild = guild
        self.current = 0
        # Disable buttons if only one page
        if len(pages) <= 1:
            for child in self.children:
                child.disabled = True

    async def update_message(self):
        content = f"🎂 BIRTHDAY LIST 🎂\n------------------------\n{self.pages[self.current]}"
        content += f"\n\nPage {self.current + 1}/{len(self.pages)}"
        try:
            await self.message.edit(content=content, view=self)
        except Exception as e:
            logger.error(f"Failed to update birthday page in guild {self.guild.name}: {e}")

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.primary)
    async def previous(self, button: Button, interaction: discord.Interaction):
        if self.current > 0:
            self.current -= 1
            await self.update_message()
        await interaction.response.defer()  # acknowledge

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.primary)
    async def next(self, button: Button, interaction: discord.Interaction):
        if self.current < len(self.pages) - 1:
            self.current += 1
            await self.update_message()
        await interaction.response.defer()  # acknowledge

# ---------------- Birthday Commands -----------------
class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="viewbirthdays", description="View the birthday list with pagination")
    async def viewbirthdays(self, interaction: discord.Interaction):
        if not await ensure_setup(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            birthdays = await get_birthdays(str(interaction.guild.id))
            if not birthdays:
                await interaction.followup.send("📂 No birthdays found yet.", ephemeral=True)
                return

            today = dt.datetime.now(dt.timezone.utc)

            # Sort upcoming birthdays
            def upcoming_sort_key(b):
                month, day = map(int, b[1].split("-"))
                if month == 2 and day == 29:
                    is_leap = today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0)
                    if not is_leap:
                        day = 28
                current = dt.datetime(today.year, month, day, tzinfo=dt.timezone.utc)
                if current < today and not is_birthday_on_date(b[1], today):
                    current = dt.datetime(today.year + 1, month, day, tzinfo=dt.timezone.utc)
                return (current - today).total_seconds()

            birthdays_sorted = sorted(birthdays, key=upcoming_sort_key)

            # Split into pages
            TEST_MODE = True  # use fake names for testing
            pages = [format_birthday_page(p, interaction.guild, test_mode=TEST_MODE) for p in paginate_birthdays(birthdays_sorted)]

            # Get or create pinned message
            pinned = [m for m in await interaction.channel.pins() if m.author.id == self.bot.user.id]
            if pinned:
                msg = pinned[0]
                await msg.edit(content=f"🎂 BIRTHDAY LIST 🎂\n------------------------\n{pages[0]}")
            else:
                msg = await interaction.channel.send(f"🎂 BIRTHDAY LIST 🎂\n------------------------\n{pages[0]}")
                await msg.pin()

            # Attach pagination view
            view = BirthdayPages(pages, msg, interaction.guild)
            await view.update_message()
            await interaction.followup.send("✅ Birthday list updated!", ephemeral=True)

        except Exception as e:
            logger.error(f"Error viewing birthday list in {interaction.guild.name}: {e}")
            await interaction.followup.send("🚨 Failed to view birthday list.", ephemeral=True)

# ---------------- Setup Cog -----------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
