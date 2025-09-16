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

def format_birthday_page(page: list[tuple[str, str]], guild: discord.Guild, test_mode: bool = False):
    today = dt.datetime.now(dt.timezone.utc)
    lines = []
    for idx, (user_id, birthday) in enumerate(page):
        if test_mode:
            name = f"User{int(user_id[-3:]):03d}"  # fake display name for test
        else:
            member = guild.get_member(int(user_id))
            name = member.display_name if member else f"<@{user_id}>"

        prefix = CONFETTI_ICON + " " if is_birthday_on_date(birthday, today) else "・"
        lines.append(f"{prefix}{name} - {format_birthday_display(birthday)}")
    return "\n".join(lines)

# ---------------- Pagination View ----------------
class BirthdayPages(View):
    def __init__(self, pages: list[str], guild: discord.Guild):
        super().__init__(timeout=180)
        self.pages = pages
        self.guild = guild
        self.current = 0
        self.message = None

        # Disable buttons if only one page
        if len(pages) <= 1:
            for child in self.children:
                child.disabled = True

    async def update_message(self, interaction: discord.Interaction):
        content = f"🎂 BIRTHDAY LIST 🎂\n------------------------\n{self.pages[self.current]}"
        content += f"\n\nPage {self.current + 1}/{len(self.pages)}"
        try:
            await interaction.edit_original_response(content=content, view=self)
        except Exception as e:
            logger.error(f"Failed to update birthday page in guild {self.guild.name}: {e}")

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                logger.debug(f"BirthdayPages message already deleted in guild {self.guild.name}")
            except Exception as e:
                logger.error(f"Unexpected error on BirthdayPages timeout in guild {self.guild.name}: {e}")

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.primary)
    async def previous(self, button: Button, interaction: discord.Interaction):
        if self.current > 0:
            self.current -= 1
        await self.update_message(interaction)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.primary)
    async def next(self, button: Button, interaction: discord.Interaction):
        if self.current < len(self.pages) - 1:
            self.current += 1
        await self.update_message(interaction)

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
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}")
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
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}")
        except Exception as e:
            logger.error(f"Error deleting birthday for {interaction.user} ({interaction.user.id}) in {interaction.guild.name}: {e}")
            await interaction.followup.send("🚨 Failed to delete birthday. Try again later.", ephemeral=True)
            return

        await interaction.followup.send("All done 🎈 Your birthday has been deleted.", ephemeral=True)

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
            birthdays_today = [str(uid) for uid, bday in birthdays if is_birthday_on_date(bday, today)]
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today, manual=True)
            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}")

            def upcoming_sort_key(b):
                month, day = map(int, b[1].split("-"))
                if month == 2 and day == 29:
                    is_leap = today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0)
                    if not is_leap:
                        day = 28
                current = dt.datetime(today.year, month, day, tzinfo=dt.timezone.utc)
                if current < today and not is_birthday_on_date(b[1], today):
                    return (dt.datetime(today.year + 1, month, day, tzinfo=dt.timezone.utc) - today).total_seconds()
                return (current - today).total_seconds()

            birthdays_sorted = sorted(birthdays, key=upcoming_sort_key)

            # --- TEST MODE ---
            TEST_MODE = True
            formatted_pages = [format_birthday_page(page, interaction.guild, test_mode=TEST_MODE)
                               for page in paginate_birthdays(birthdays_sorted)]

            guild_config = await get_guild_config(str(interaction.guild.id))
            check_hour = guild_config.get("check_hour", 9)

            if len(formatted_pages) == 1:
                content = f"🎂 BIRTHDAY LIST 🎂\n------------------------\n{formatted_pages[0]}\n\n-# 💡 Tip: Use /setbirthday to add your own special day!\n-# ⏰ Bot checks birthdays daily at {check_hour}:00 UTC"
                await interaction.edit_original_response(content=content)
            else:
                formatted_pages[0] += f"\n\n-# 💡 Tip: Use /setbirthday to add your own special day!\n-# ⏰ Bot checks birthdays daily at {check_hour}:00 UTC"
                view = BirthdayPages(formatted_pages, interaction.guild)
                content = f"🎂 BIRTHDAY LIST 🎂\n------------------------\n{formatted_pages[0]}"
                await interaction.edit_original_response(content=content, view=view)
                view.message = await interaction.original_response()  # store for timeout edits

        except Exception as e:
            logger.error(f"Error viewing birthday list by {interaction.user} ({interaction.user.id}) in {interaction.guild.name}: {e}")
            await interaction.followup.send("🚨 Failed to view birthday list. Try again later.", ephemeral=True)

# ---------------- Setup Cog ----------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
