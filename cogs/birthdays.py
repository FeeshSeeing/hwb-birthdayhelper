import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from database import set_birthday, delete_birthday, get_guild_config, get_birthdays
from utils import parse_day_month_input, format_birthday_display, update_pinned_birthday_message, is_birthday_on_date
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

# ---------------- Pagination Helpers ----------------
def paginate_birthdays(birthdays: list[tuple[str, str]], per_page: int = ENTRIES_PER_PAGE):
    return [birthdays[i:i + per_page] for i in range(0, len(birthdays), per_page)]

def format_birthday_page(page: list[tuple[str, str]], guild: discord.Guild):
    today = dt.datetime.now(dt.timezone.utc)
    lines = []
    for user_id, birthday in page:
        member = guild.get_member(int(user_id))
        name = member.display_name if member else f"<@{user_id}>"
        prefix = CONFETTI_ICON + " " if is_birthday_on_date(birthday, today) else "・"
        lines.append(f"{prefix}{name} - {format_birthday_display(birthday)}")
    return "\n".join(lines)

# ---------------- Pagination View ----------------
class BirthdayPages(View):
    def __init__(self, pages: list[str], message: discord.Message, guild: discord.Guild):
        super().__init__(timeout=None)
        self.pages = pages
        self.message = message
        self.guild = guild
        self.current = 0
        self.update_buttons()

    def update_buttons(self):
        for child in self.children:
            if child.label == "⬅️":
                child.disabled = self.current == 0
            elif child.label == "➡️":
                child.disabled = self.current == len(self.pages) - 1

    async def update_message(self):
        content = f"🎂 BIRTHDAY LIST 🎂\n------------------------\n{self.pages[self.current]}"
        content += f"\n\nPage {self.current + 1}/{len(self.pages)}"
        self.update_buttons()
        try:
            await self.message.edit(content=content, view=self)
        except Exception as e:
            logger.error(f"Failed to update birthday page in guild {self.guild.name}: {e}")

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.primary)
    async def previous(self, button: Button, interaction: discord.Interaction):
        if self.current > 0:
            self.current -= 1
            await self.update_message()
        await interaction.response.defer()

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.primary)
    async def next(self, button: Button, interaction: discord.Interaction):
        if self.current < len(self.pages) - 1:
            self.current += 1
            await self.update_message()
        await interaction.response.defer()

# ---------------- Birthday Commands ----------------
class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setbirthday", description="Set your birthday (day then month)")
    @app_commands.describe(day="Day of birthday", month="Month of birthday")
    async def setbirthday(self, interaction: discord.Interaction, day: int, month: int):
        if not await ensure_setup(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        result = parse_day_month_input(day, month)
        if not result:
            await interaction.followup.send("❗ Invalid day/month! Example: 25 12", ephemeral=True)
            return
        day, month = result
        birthday_str = f"{month:02d}-{day:02d}"

        try:
            await set_birthday(str(interaction.guild.id), str(interaction.user.id), birthday_str)
            all_birthdays = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [str(uid) for uid, bday in all_birthdays if is_birthday_on_date(bday, today)]
            await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
        except Exception as e:
            logger.error(f"Error setting birthday for {interaction.user} ({interaction.user.id}) in {interaction.guild.name}: {e}")
            await interaction.followup.send("🚨 Failed to set birthday. Try again later.", ephemeral=True)
            return

        human_readable = format_birthday_display(birthday_str)
        await interaction.followup.send(f"All done 💌 Your special day is marked as {human_readable}. Hugs are on the way!", ephemeral=True)

    @app_commands.command(name="deletebirthday", description="Delete your birthday")
    async def deletebirthday(self, interaction: discord.Interaction):
        if not await ensure_setup(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await delete_birthday(str(interaction.guild.id), str(interaction.user.id))
            all_birthdays = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [str(uid) for uid, bday in all_birthdays if is_birthday_on_date(bday, today)]
            await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
        except Exception as e:
            logger.error(f"Error deleting birthday for {interaction.user} ({interaction.user.id}) in {interaction.guild.name}: {e}")
            await interaction.followup.send("🚨 Failed to delete birthday. Try again later.", ephemeral=True)
            return

        await interaction.followup.send("All done 🎈 Your birthday has been deleted.", ephemeral=True)

    @app_commands.command(name="viewbirthdays", description="View the next 20 upcoming birthdays")
    async def viewbirthdays(self, interaction: discord.Interaction):
        if not await ensure_setup(interaction):
            return

        await interaction.response.defer()
        try:
            birthdays = await get_birthdays(str(interaction.guild.id))
            if not birthdays:
                await interaction.followup.send("📂 No birthdays found yet.", ephemeral=True)
                return

            today = dt.datetime.now(dt.timezone.utc)

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
            pages = [format_birthday_page(p, interaction.guild) for p in paginate_birthdays(birthdays_sorted)]

            # Get pinned message or create one
            pinned_messages = [m for m in await interaction.channel.pins() if m.author.id == self.bot.user.id]
            if pinned_messages:
                msg = pinned_messages[0]
                await msg.edit(content=f"🎂 BIRTHDAY LIST 🎂\n------------------------\n{pages[0]}")
            else:
                msg = await interaction.channel.send(f"🎂 BIRTHDAY LIST 🎂\n------------------------\n{pages[0]}")
                await msg.pin()

            if len(pages) > 1:
                view = BirthdayPages(pages, msg, interaction.guild)
                await view.update_message()

        except Exception as e:
            logger.error(f"Error viewing birthday list in {interaction.guild.name}: {e}")
            await interaction.followup.send("🚨 Failed to view birthday list. Try again later.", ephemeral=True)

# ---------------- Setup Cog ----------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
