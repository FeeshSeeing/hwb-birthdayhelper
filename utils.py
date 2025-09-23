import calendar
import discord
import datetime as dt
from logger import logger
from discord.ui import View, Button

MAX_PINNED_ENTRIES = 20  # Show first 20 in pinned message
CONFETTI_ICON = "🎉 "


def parse_day_month_input(day_input, month_input):
    """Parse user input for day and month into integers."""
    try:
        day = int(day_input)
        month = int(month_input)
        if 1 <= day <= 31 and 1 <= month <= 12:
            return day, month
    except ValueError:
        pass
    return None


def format_birthday_display(birthday_str):
    """Convert 'MM-DD' into a readable format with suffix."""
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
    """Check if a birthday occurs on the given date (handles Feb 29)."""
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

        if len(self.pages) > 1:
            self.previous_button = Button(label="⬅️", style=discord.ButtonStyle.primary, disabled=True)
            self.next_button = Button(label="➡️", style=discord.ButtonStyle.primary)
            self.previous_button.callback = self.previous
            self.next_button.callback = self.next
            self.add_item(self.previous_button)
            self.add_item(self.next_button)
        else:
            self.previous_button = None
            self.next_button = None

    async def update_message(self, interaction: discord.Interaction):
        if self.previous_button and self.next_button:
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
        content += "\n\n"
        content += "-# 💡 Tip: Use /setbirthday to add your own special day!\n"
        content += f"-# ⏰ Bot checks birthdays daily at {self.check_hour}:00 UTC"
        if len(self.pages) > 1:
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
    db,
    highlight_today: list[str] = None,
    manual: bool = False
) -> discord.Message | None:
    """Update (or create) the pinned birthday message with content + buttons."""

    # Fetch guild config from the db instance
    guild_config = await db.get_guild_config(str(guild.id))
    if not guild_config:
        logger.warning(f"No guild config for {guild.name}, skipping pinned message update.")
        return None

    try:
        channel_id = int(guild_config["channel_id"])
    except (TypeError, ValueError):
        logger.error(f"Invalid channel ID for {guild.name}: {guild_config.get('channel_id')}")
        return None

    channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
    perms = channel.permissions_for(guild.me)
    if not perms.send_messages:
        logger.error(f"Cannot send messages in channel {channel.name} ({channel.id})")
        return None

    check_hour = guild_config.get("check_hour", 9)
    birthdays = await db.get_birthdays(str(guild.id))
    today = dt.datetime.now(dt.timezone.utc)

    # ---------------- Fetch existing pinned message ----------------
    pinned_msg = None
    async with db.db.execute(
        "SELECT value FROM config WHERE key=?", (f"pinned_birthday_msg_{str(guild.id)}",)
    ) as cursor:
        result = await cursor.fetchone()
    if result:
        try:
            pinned_msg_id = int(result[0])
            pinned_msg = await channel.fetch_message(pinned_msg_id)
        except discord.NotFound:
            pinned_msg = None

    # ---------------- Build content ----------------
    if not birthdays:
        content = "🎂 BIRTHDAY LIST 🎂\n------------------------\n```yaml\nNo birthdays found!\n```"
        view_to_use = None
    else:
        # Safe upcoming_sort_key that handles Feb 29
        def upcoming_sort_key(b):
            month, day = map(int, b[1].split("-"))
            year = today.year

            # Adjust Feb 29 on non-leap years
            if month == 2 and day == 29:
                is_leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
                if not is_leap:
                    day = 28

            try:
                current_year_birthday = dt.datetime(year, month, day, tzinfo=dt.timezone.utc)
            except ValueError:
                current_year_birthday = dt.datetime(year + 1, month, day, tzinfo=dt.timezone.utc)

            # If birthday already passed this year (and today isn’t their birthday), use next year
            if current_year_birthday < today and not is_birthday_on_date(b[1], today):
                next_year_birthday = dt.datetime(year + 1, month, day, tzinfo=dt.timezone.utc)
                return (next_year_birthday - today).total_seconds()

            return (current_year_birthday - today).total_seconds()

        sorted_birthdays = sorted(birthdays, key=upcoming_sort_key)
        pages = [sorted_birthdays[i:i + MAX_PINNED_ENTRIES] for i in range(0, len(sorted_birthdays), MAX_PINNED_ENTRIES)]
        view = BirthdayPages(pages, guild, check_hour)
        view.current = 0

        page_content = []
        for uid, bday in pages[0]:
            member = guild.get_member(int(uid))
            name = member.display_name if member else f"<@{uid}>"
            prefix = "・" + (CONFETTI_ICON if is_birthday_on_date(bday, today) else "")
            page_content.append(f"{prefix}{name} - {format_birthday_display(bday)}")

        content = "🎂 BIRTHDAY LIST 🎂\n------------------------\n" + "\n".join(page_content)
        content += "\n\n-# 💡 Tip: Use /setbirthday to add your own special day!\n"
        content += f"-# ⏰ Bot checks birthdays daily at {check_hour}:00 UTC"
        if len(pages) > 1:
            content += f"\n\nPage 1/{len(pages)}"

        view_to_use = view

    # ---------------- Edit or Send ----------------
    try:
        if pinned_msg:
            await pinned_msg.edit(content=content, view=view_to_use)
        else:
            pinned_msg = await channel.send(content=content, view=view_to_use)
            if perms.manage_messages:
                try:
                    await pinned_msg.pin()
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Failed to update pinned message in {guild.name}: {e}")
        pinned_msg = None

    # ---------------- Save pinned message ID ----------------
    if pinned_msg:
        await db.db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (f"pinned_birthday_msg_{guild.id}", str(pinned_msg.id))
        )
        await db.db.commit()

    return pinned_msg


# ---------------- Ensure Setup ----------------
async def ensure_setup(interaction: discord.Interaction, db=None) -> bool:
    """
    Ensure the command is used in a guild and that the guild has a valid configuration.

    Returns:
        bool: True if the guild is ready, False otherwise.
    """

    # 1️- Prevent using commands in DMs
    if interaction.guild is None:
        try:
            await interaction.response.send_message(
                "📬 **Hey there!**\n"
                "I can only work inside servers\n"
                "Try running this command in one of your servers where I'm installed.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Failed to send DM-block message: {e}", exc_info=True)
        return False

    # 2️- Use provided DB or fallback to bot.db
    db = db or getattr(interaction.client, "db", None)
    if db is None:
        logger.error("No database instance available for ensure_setup()")
        return False

    # 3️- Check if the server is configured
    guild_config = await db.get_guild_config(interaction.guild.id)
    if not guild_config:
        try:
            await interaction.response.send_message(
                "❗ This server hasn't been set up yet.\n"
                "Ask an admin to run `/setup` so I can start tracking birthdays. 🥳",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Failed to send setup prompt: {e}", exc_info=True)
        return False

    return True