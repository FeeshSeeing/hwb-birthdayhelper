import discord
from discord import app_commands
from discord.ext import commands, tasks
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

def format_birthday_page(page: list[tuple[str, str]], guild: discord.Guild, current_page: int, total_pages: int):
    today = dt.datetime.now(dt.timezone.utc)
    lines = []
    for user_id, birthday in page:
        member = guild.get_member(int(user_id))
        name = member.display_name if member else f"<@{user_id}>"
        prefix = CONFETTI_ICON + " " if is_birthday_on_date(birthday, today) else "・"
        lines.append(f"{prefix}{name} - {format_birthday_display(birthday)}")

    content = f"🎂 BIRTHDAY LIST 🎂\n------------------------\n" + "\n".join(lines)
    content += f"\nPage {current_page + 1}/{total_pages}"
    # NOTE: do NOT append tips here. Tips will be appended AFTER the View in the message send/edit
    return content

# ---------------- Pagination View ----------------
class BirthdayPages(View):
    def __init__(self, pages: list[list[tuple[str, str]]], guild: discord.Guild, check_hour: int):
        super().__init__(timeout=None)  # pinned messages stay forever
        self.pages = pages
        self.guild = guild
        self.check_hour = check_hour
        self.current = 0

        # Create buttons dynamically
        self.previous_button = Button(label="⬅️", style=discord.ButtonStyle.primary, disabled=True)
        self.next_button = Button(label="➡️", style=discord.ButtonStyle.primary)

        self.previous_button.callback = self.previous
        self.next_button.callback = self.next

        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    async def update_message(self, interaction: discord.Interaction):
        # Update button states
        self.previous_button.disabled = self.current == 0
        self.next_button.disabled = self.current >= len(self.pages) - 1

        content = format_birthday_page(
            self.pages[self.current],
            self.guild,
            self.current,
            len(self.pages)
        )

        # Append tips **after the View** (buttons)
        content_with_tips = content + f"\n\n-#💡 Tip: Use /setbirthday to add your own special day!\n-#⏰ Bot checks birthdays daily at {self.check_hour}:00 UTC"

        try:
            await interaction.response.edit_message(content=content_with_tips, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(content=content_with_tips, view=self)

    async def previous(self, interaction: discord.Interaction):
        if self.current > 0:
            self.current -= 1
        await self.update_message(interaction)

    async def next(self, interaction: discord.Interaction):
        if self.current < len(self.pages) - 1:
            self.current += 1
        await self.update_message(interaction)

# ---------------- Birthday Commands ----------------
class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.refresh_pinned_messages.start()

    # ---------------- Daily Refresh ----------------
    @tasks.loop(hours=24)
    async def refresh_pinned_messages(self):
        for guild in self.bot.guilds:
            try:
                birthdays = await get_birthdays(str(guild.id))
                today = dt.datetime.now(dt.timezone.utc)
                birthdays_today = [str(uid) for uid, bday in birthdays if is_birthday_on_date(bday, today)]
                await update_pinned_birthday_message(guild, highlight_today=birthdays_today)
            except Exception as e:
                logger.error(f"Failed daily pinned refresh in {guild.name}: {e}")

    @refresh_pinned_messages.before_loop
    async def before_refresh(self):
        await self.bot.wait_until_ready()

    # ---------------- Commands ----------------
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
            logger.error(f"Error setting birthday: {e}")
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
            logger.error(f"Error deleting birthday: {e}")
            await interaction.followup.send("🚨 Failed to delete birthday. Try again later.", ephemeral=True)
            return
        await interaction.followup.send("All done 🎈 Your birthday has been deleted.", ephemeral=True)

    @app_commands.command(name="viewbirthdays", description="View upcoming birthdays (first 20)")
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
            await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today, manual=True)

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
            first_page = birthdays_sorted[:ENTRIES_PER_PAGE]

            guild_config = await get_guild_config(str(interaction.guild.id))
            check_hour = guild_config.get("check_hour", 7)

            content = "🎂 BIRTHDAY LIST 🎂\n------------------------\n"
            content += "\n".join([
                f"{CONFETTI_ICON if is_birthday_on_date(bday, today) else '・'} "
                f"{interaction.guild.get_member(int(uid)).display_name if interaction.guild.get_member(int(uid)) else f'<@{uid}>'} - {format_birthday_display(bday)}"
                for uid, bday in first_page
            ])
            content += f"\n\n💡 Tip: Use /setbirthday to add your own special day!\n⏰ Bot checks birthdays daily at {check_hour}:00 UTC"

            await interaction.followup.send(content=content, ephemeral=True)

        except Exception as e:
            logger.error(f"Error viewing birthdays: {e}")
            await interaction.followup.send("🚨 Failed to view birthday list. Try again later.", ephemeral=True)

# ---------------- Setup Cog ----------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
