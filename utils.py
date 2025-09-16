import calendar
import aiosqlite
import discord
import datetime as dt
from config import DB_FILE
from database import get_birthdays, get_guild_config
from logger import logger
from discord.ui import View, Button

MAX_PINNED_ENTRIES = 20  # Show first 20 in pinned message
CONFETTI_ICON = "🎉"


def parse_day_month_input(day_input, month_input):
    try:
        day = int(day_input)
        month = int(month_input)
        if 1 <= day <= 31 and 1 <= month <= 12:
            return day, month
    except ValueError:
        pass
    return None


def format_birthday_display(birthday_str):
    try:
        month_str, day_str = birthday_str.split("-")
        month, day = int(month_str), int(day_str)
        month_name = calendar.month_name[month]
        if 4 <= day <= 20 or 24 <= day <= 30:
            suffix = "th"
        else:
            suffix = ["st", "nd", "rd"][(day % 10) - 1] if 1 <= day % 10 <= 3 else "th"
        return f"{day}{suffix} {month_name}"
    except Exception as e:
        logger.error(f"Error formatting birthday '{birthday_str}': {e}")
        return birthday_str


def is_birthday_on_date(birthday_str: str, check_date: dt.datetime) -> bool:
    b_month, b_day = map(int, birthday_str.split("-"))
    if b_month == 2 and b_day == 29:
        is_leap_year = (check_date.year % 4 == 0 and (check_date.year % 100 != 0 or check_date.year % 400 == 0))
        return (check_date.month == 2 and check_date.day == 29 and is_leap_year) or \
               (check_date.month == 2 and check_date.day == 28 and not is_leap_year)
    return check_date.month == b_month and check_date.day == b_day


# ---------------- Pagination View ----------------
class BirthdayPages(discord.ui.View):
    def __init__(self, pages: list[list[tuple[str, str]]], guild: discord.Guild, check_hour: int):
        super().__init__(timeout=None)
        self.pages = pages
        self.guild = guild
        self.check_hour = check_hour
        self.current = 0

        self.previous_button = Button(label="⬅️", style=discord.ButtonStyle.primary, disabled=True)
        self.next_button = Button(label="➡️", style=discord.ButtonStyle.primary)
        self.previous_button.callback = self.previous
        self.next_button.callback = self.next
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    async def update_message(self, interaction: discord.Interaction):
        self.previous_button.disabled = self.current == 0
        self.next_button.disabled = self.current >= len(self.pages) - 1

        today = dt.datetime.now(dt.timezone.utc)
        page_content = []
        for user_id, birthday in self.pages[self.current]:
            member = self.guild.get_member(int(user_id))
            name = member.display_name if member else f"<@{user_id}>"
            prefix = "・" + (CONFETTI_ICON if is_birthday_on_date(birthday, today) else "")
            page_content.append(f"{prefix}{name} - {format_birthday_display(birthday)}")

        content = "🎂 BIRTHDAY LIST 🎂\n------------------------\n"
        content += "\n".join(page_content)
        content += "\n\n"  # extra spacing before footer
        content += "-# 💡 Tip: Use /setbirthday to add your own special day!\n"
        content += f"-# ⏰ Bot checks birthdays daily at {self.check_hour}:00 UTC"
        content += f"\n\nPage {self.current + 1}/{len(self.pages)}"

        try:
            await interaction.response.edit_message(content=content, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(content=content, view=self)

    async def previous(self, interaction: discord.Interaction):
        if self.current > 0:
            self.current -= 1
        await self.update_message(interaction)

    async def next(self, interaction: discord.Interaction):
        if self.current < len(self.pages) - 1:
            self.current += 1
        await self.update_message(interaction)

# ---------------- Update Pinned Birthday Message ----------------
async def update_pinned_birthday_message(
    guild: discord.Guild,
    highlight_today: list[str] = None,
    manual: bool = False
) -> discord.Message | None:
    """Update (or create if missing) the pinned birthday message, with buttons and footer."""

    guild_config = await get_guild_config(str(guild.id))
    if not guild_config:
        logger.warning(f"No guild config for {guild.name}, skipping pinned message update.")
        return None

    try:
        channel_id = int(guild_config["channel_id"])
    except (TypeError, ValueError):
        logger.error(f"Invalid channel ID in guild config for {guild.name}: {guild_config.get('channel_id')}")
        return None

    channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
    perms = channel.permissions_for(guild.me)
    if not perms.send_messages:
        logger.error(f"Cannot send messages in channel {channel.name} ({channel.id})")
        return None

    check_hour = guild_config.get("check_hour", 9)
    birthdays = await get_birthdays(str(guild.id))
    today = dt.datetime.now(dt.timezone.utc)

    if not birthdays:
        content = "🎂 BIRTHDAY LIST 🎂\n------------------------\n```yaml\nNo birthdays found!\n```"
        pinned_msg = await channel.send(content)
        if perms.manage_messages:
            await pinned_msg.pin()
        return pinned_msg

    # --- Sort birthdays ---
    def upcoming_sort_key(b):
        month, day = map(int, b[1].split("-"))
        if month == 2 and day == 29:
            is_leap = today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0)
            if not is_leap:
                day = 28
        try:
            current_year_birthday = dt.datetime(today.year, month, day, tzinfo=dt.timezone.utc)
        except ValueError:
            current_year_birthday = dt.datetime(today.year + 1, month, day, tzinfo=dt.timezone.utc)
        if current_year_birthday < today and not is_birthday_on_date(b[1], today):
            return (dt.datetime(today.year + 1, month, day, tzinfo=dt.timezone.utc) - today).total_seconds()
        return (current_year_birthday - today).total_seconds()

    sorted_birthdays = sorted(birthdays, key=upcoming_sort_key)

    # --- Pagination ---
    pages = [sorted_birthdays[i:i + MAX_PINNED_ENTRIES] for i in range(0, len(sorted_birthdays), MAX_PINNED_ENTRIES)]
    view = BirthdayPages(pages, guild, check_hour)

    pinned_msg = None
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM config WHERE key=?", (f"pinned_birthday_msg_{guild.id}",)) as cursor:
            result = await cursor.fetchone()
        if result:
            try:
                pinned_msg_id = int(result[0])
                pinned_msg = await channel.fetch_message(pinned_msg_id)
            except discord.NotFound:
                pinned_msg = None

        if pinned_msg:
            try:
                await pinned_msg.edit(view=view)
            except Exception as e:
                logger.warning(f"Failed to edit pinned message in {guild.name}: {e}")
                pinned_msg = None

        if not pinned_msg:
            pinned_msg = await channel.send(view=view)
            if perms.manage_messages:
                try:
                    await pinned_msg.pin()
                except Exception:
                    pass

        # Store pinned message ID
        await db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (f"pinned_birthday_msg_{guild.id}", str(pinned_msg.id))
        )
        await db.commit()

    return pinned_msg