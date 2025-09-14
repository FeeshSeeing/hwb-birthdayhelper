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
        prefix = CONFETTI_ICON + " " if is_birthday_on_date(birthday, today) else "✦ "
        lines.append(f"{prefix}{name}: {format_birthday_display(birthday)}")
    return "\n".join(lines)

# ---------------- Pagination View ----------------
class BirthdayPages(View):
    def __init__(self, pages: list[str], guild: discord.Guild):
        super().__init__(timeout=180)
        self.pages = pages
        self.guild = guild
        self.current = 0
        if len(pages) <= 1:
            for child in self.children:
                child.disabled = True

    async def update_message(self, interaction: discord.Interaction):
        content = f"**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**\n"
        content += self.pages[self.current]
        content += f"\n\nPage {self.current + 1}/{len(self.pages)}"
        await interaction.response.edit_message(content=content, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if hasattr(self, 'message') and self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                logger.debug(f"BirthdayPages message already deleted in guild {self.guild.name}")
            except discord.HTTPException as e:
                logger.error(f"Error editing message on timeout in guild {self.guild.name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error on BirthdayPages timeout in guild {self.guild.name}: {e}")

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.primary)
    async def previous(self, button: Button, interaction: discord.Interaction):
        if self.current > 0:
            self.current -= 1
            await self.update_message(interaction)
        else:
            button.disabled = True
            await interaction.response.edit_message(view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.primary)
    async def next(self, button: Button, interaction: discord.Interaction):
        if self.current < len(self.pages) - 1:
            self.current += 1
            await self.update_message(interaction)
        else:
            button.disabled = True
            await interaction.response.edit_message(view=self)

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
            logger.warning(f"Invalid birthday input '{day} {month}' from {interaction.user} in {interaction.guild.name}")
            return

        day, month = result
        birthday_str = f"{month:02d}-{day:02d}"

        try:
            # Save birthday
            await set_birthday(str(interaction.guild.id), str(interaction.user.id), birthday_str)

            # Fetch fresh data
            all_birthdays_in_guild = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [str(uid) for uid, bday in all_birthdays_in_guild if is_birthday_on_date(bday, today)]

            # Update pinned message
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                    logger.info(f"Pinned birthday message for guild {interaction.guild.name} after setbirthday.")
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}, missing permission.")

        except Exception as e:
            logger.error(f"Error setting birthday for {interaction.user} ({interaction.user.id}) in {interaction.guild.name}: {e}")
            await interaction.followup.send("🚨 Failed to set birthday. Try again later.", ephemeral=True)
            return

        human_readable = format_birthday_display(birthday_str)
        logger.info(f"🎂 {interaction.user} ({interaction.user.id}) set birthday to {human_readable} in {interaction.guild.name}")
        await interaction.followup.send(
            f"All done 💌 Your special day is marked as {human_readable}. Hugs are on the way!",
            ephemeral=True
        )

    @app_commands.command(name="deletebirthday", description="Delete your birthday")
    async def deletebirthday(self, interaction: discord.Interaction):
        if not await ensure_setup(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await delete_birthday(str(interaction.guild.id), str(interaction.user.id))

            # Fetch fresh data
            all_birthdays_in_guild = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [str(uid) for uid, bday in all_birthdays_in_guild if is_birthday_on_date(bday, today)]

            # Update pinned message
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                    logger.info(f"Pinned birthday message for guild {interaction.guild.name} after deletebirthday.")
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}, missing permission.")

        except Exception as e:
            logger.error(f"Error deleting birthday for {interaction.user} ({interaction.user.id}) in {interaction.guild.name}: {e}")
            await interaction.followup.send("🚨 Failed to delete birthday. Try again later.", ephemeral=True)
            return

        logger.info(f"🗑️ {interaction.user} ({interaction.user.id}) deleted their birthday in {interaction.guild.name}")
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
            birthdays_today_list = [str(uid) for uid, bday in birthdays if is_birthday_on_date(bday, today)]

            # Update pinned message
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today_list, manual=True)
            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                    logger.info(f"Pinned birthday message for guild {interaction.guild.name} after viewbirthdays.")
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}, missing permission.")

            # Sort and paginate
            def upcoming_sort_key(b):
                month, day = map(int, b[1].split("-"))
                if month == 2 and day == 29:
                    is_leap = (today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0))
                    if not is_leap:
                        day = 28
                try:
                    current_year_birthday = dt.datetime(today.year, month, day, tzinfo=dt.timezone.utc)
                except ValueError:
                    current_year_birthday = dt.datetime(today.year + 1, month, day, tzinfo=dt.timezone.utc)
                if current_year_birthday < today and not is_birthday_on_date(b[1], today):
                    try:
                        next_year_birthday = dt.datetime(today.year + 1, month, day, tzinfo=dt.timezone.utc)
                    except ValueError:
                        return float('inf')
                    return (next_year_birthday - today).total_seconds()
                return (current_year_birthday - today).total_seconds()

            birthdays_sorted = sorted(birthdays, key=upcoming_sort_key)
            guild_config = await get_guild_config(str(interaction.guild.id))
            check_hour = guild_config.get("check_hour", 9)
            check_hour_info = f"_Bot checks birthdays daily at {check_hour}:00 UTC_"

            formatted_pages = [format_birthday_page(page, interaction.guild) for page in paginate_birthdays(birthdays_sorted, per_page=ENTRIES_PER_PAGE)]
            if len(formatted_pages) <= 1:
                content = f"**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**\n{formatted_pages[0]}\n\n_- Tip: Use /setbirthday to add your own special day._\n{check_hour_info}"
                await interaction.followup.send(content=content, ephemeral=True)
            else:
                formatted_pages[0] += f"\n\n_- Tip: Use /setbirthday to add your own special day._\n{check_hour_info}"
                view = BirthdayPages(formatted_pages, interaction.guild)
                content = f"**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**\n{formatted_pages[0]}"
                msg = await interaction.followup.send(content=content, view=view, ephemeral=True)
                view.message = await msg.original_response()

        except Exception as e:
            logger.error(f"Error viewing birthday list by {interaction.user} ({interaction.user.id}) in {interaction.guild.name}: {e}")
            await interaction.followup.send("🚨 Failed to view birthday list. Try again later.", ephemeral=True)

# ---------------- Setup Cog ----------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
