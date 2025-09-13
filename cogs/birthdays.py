import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from database import set_birthday, delete_birthday, get_guild_config, get_birthdays
from utils import parse_day_month_input, format_birthday_display, update_pinned_birthday_message
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
        month, day = map(int, birthday.split("-"))
        prefix = CONFETTI_ICON + " " if month == today.month and day == today.day else "✦ "
        lines.append(f"{prefix}{name}: {format_birthday_display(birthday)}")
    return "\n".join(lines)

# ---------------- Pagination View ----------------
class BirthdayPages(View):
    def __init__(self, pages, guild: discord.Guild):
        super().__init__(timeout=120)
        self.pages = pages
        self.guild = guild
        self.current = 0

    async def update_message(self, interaction: discord.Interaction):
        content = f"**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**\n"
        content += format_birthday_page(self.pages[self.current], self.guild)
        content += f"\n\nPage {self.current + 1}/{len(self.pages)}"
        await interaction.response.edit_message(content=content, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

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

    # ---------------- Set Birthday ----------------
    @app_commands.command(name="setbirthday", description="Set your birthday (day then month)")
    @app_commands.describe(day="Day of birthday", month="Month of birthday")
    async def setbirthday(self, interaction: discord.Interaction, day: int, month: int):
        if not await ensure_setup(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        result = parse_day_month_input(day, month)
        if not result:
            await interaction.followup.send("❗ Invalid day/month! Example: 25 12", ephemeral=True)
            logger.warning(f"Invalid birthday input from {interaction.user} in {interaction.guild.name}")
            return

        day, month = result
        birthday_str = f"{month:02d}-{day:02d}"
        try:
            await set_birthday(str(interaction.guild.id), str(interaction.user.id), birthday_str)
            # Refresh pinned message immediately
            birthdays = await get_birthdays(str(interaction.guild.id))
            birthdays_today = [
                user_id for user_id, bday in birthdays
                if int(bday.split("-")[0]) == dt.datetime.now(dt.timezone.utc).month
                and int(bday.split("-")[1]) == dt.datetime.now(dt.timezone.utc).day
            ]
            await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
        except Exception as e:
            logger.error(f"Error setting birthday for {interaction.user}: {e}")
            await interaction.followup.send("🚨 Failed to set birthday. Try again later.", ephemeral=True)
            return

        human_readable = format_birthday_display(birthday_str)
        logger.info(f"🎂 {interaction.user} set birthday to {human_readable} in {interaction.guild.name}")
        await interaction.followup.send(
            f"All done 💌 Your special day is marked as {human_readable}. Hugs are on the way!\n"
            f"_- Tip: Use /setbirthday to add your own special day._",
            ephemeral=True
        )

    # ---------------- Delete Birthday ----------------
    @app_commands.command(name="deletebirthday", description="Delete your birthday")
    async def deletebirthday(self, interaction: discord.Interaction):
        if not await ensure_setup(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await delete_birthday(str(interaction.guild.id), str(interaction.user.id))
            # Refresh pinned message immediately
            birthdays = await get_birthdays(str(interaction.guild.id))
            birthdays_today = [
                user_id for user_id, bday in birthdays
                if int(bday.split("-")[0]) == dt.datetime.now(dt.timezone.utc).month
                and int(bday.split("-")[1]) == dt.datetime.now(dt.timezone.utc).day
            ]
            await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
        except Exception as e:
            logger.error(f"Error deleting birthday for {interaction.user}: {e}")
            await interaction.followup.send("🚨 Failed to delete birthday. Try again later.", ephemeral=True)
            return

        logger.info(f"🗑️ {interaction.user} deleted their birthday in {interaction.guild.name}")
        await interaction.followup.send("All done 🎈 Your birthday has been deleted.", ephemeral=True)

    # ---------------- View Birthdays ----------------
    @app_commands.command(name="viewbirthdays", description="View the birthday list and refresh the pinned message")
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
            birthdays_today = [
                user_id for user_id, bday in birthdays
                if int(bday.split("-")[0]) == today.month and int(bday.split("-")[1]) == today.day
            ]
            # Refresh pinned message while preserving confetti
            await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today, manual=True)

            # Sort upcoming birthdays
            def upcoming_sort_key(b):
                month, day = map(int, b[1].split("-"))
                delta = (month - today.month) * 31 + (day - today.day)
                return delta if delta >= 0 else delta + 12 * 31
            birthdays_sorted = sorted(birthdays, key=upcoming_sort_key)

            if len(birthdays_sorted) <= ENTRIES_PER_PAGE:
                content = f"**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**\n{format_birthday_page(birthdays_sorted, interaction.guild)}"
                await interaction.followup.send(content=content, ephemeral=True)
            else:
                pages = paginate_birthdays(birthdays_sorted, per_page=ENTRIES_PER_PAGE)
                view = BirthdayPages(pages, interaction.guild)
                content = f"**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**\n{format_birthday_page(pages[0], interaction.guild)}"
                msg = await interaction.followup.send(content=content, view=view, ephemeral=True)
                view.message = await msg.original_response()

        except Exception as e:
            logger.error(f"Error viewing pinned birthday list by {interaction.user}: {e}")
            await interaction.followup.send("🚨 Failed to view birthday list. Try again later.", ephemeral=True)

# ---------------- Setup Cog ----------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
