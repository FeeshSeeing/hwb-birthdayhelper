import calendar
import aiosqlite
import discord
import datetime as dt
from config import DB_FILE
from database import get_birthdays, get_guild_config
from logger import logger

MAX_PINNED_ENTRIES = 20  # Entries per page in pinned message
CONFETTI_ICON = "🎉"

# ---------------- Helpers ----------------
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

# ---------------- Pagination ----------------
def paginate_birthdays(birthdays: list[tuple[str, str]], per_page: int = MAX_PINNED_ENTRIES):
    return [birthdays[i:i + per_page] for i in range(0, len(birthdays), per_page)]

def build_pinned_page(page: list[tuple[str, str]], guild: discord.Guild, highlight_today: list[str] = None, current_page: int = 0, total_pages: int = 1, check_hour: int = 7) -> str:
    today = dt.datetime.now(dt.timezone.utc)
    lines = ["🎂 BIRTHDAY LIST 🎂", "------------------------"]

    for user_id, birthday in page:
        member = guild.get_member(int(user_id))
        name = member.display_name if member else f"<@{user_id}>"
        if highlight_today and str(user_id) in map(str, highlight_today):
            name = f"{CONFETTI_ICON} {name}"
        prefix = "" if highlight_today and str(user_id) in map(str, highlight_today) else "・"
        lines.append(f"{prefix}{name} - {format_birthday_display(birthday)}")

    lines.append("")  # space before buttons
    lines.append(f"Page {current_page + 1}/{total_pages}")
    lines.append("\n-#💡 Tip: Use /setbirthday to add your own special day!")
    lines.append(f"-#⏰ Bot checks birthdays daily at {check_hour}:00 UTC")

    return "\n".join(lines)

# ---------------- Pinned Message Update ----------------
async def update_pinned_birthday_message(
    guild: discord.Guild,
    highlight_today: list[str] = None,
    manual: bool = False
) -> discord.Message | None:
    """Update (or create) the paginated pinned birthday message."""
    guild_config = await get_guild_config(str(guild.id))
    if not guild_config:
        logger.warning(f"No guild config for {guild.name}, skipping pinned message update.")
        return None

    try:
        channel_id = int(guild_config["channel_id"])
    except (TypeError, ValueError):
        logger.error(f"Invalid channel ID for {guild.name}: {guild_config.get('channel_id')}")
        return None

    # --- Fetch channel ---
    channel = guild.get_channel(channel_id)
    if not channel:
        try:
            channel = await guild.fetch_channel(channel_id)
        except Exception as e:
            logger.error(f"Cannot fetch channel {channel_id} in {guild.name}: {e}")
            return None

    perms = channel.permissions_for(guild.me)
    if not perms.send_messages:
        logger.error(f"Bot cannot send messages in channel {channel.name} ({guild.name}).")
        return None

    birthdays = await get_birthdays(str(guild.id))
    today = dt.datetime.now(dt.timezone.utc)
    check_hour = guild_config.get("check_hour", 7)

    if not birthdays:
        content = "🎂 BIRTHDAY LIST 🎂\n------------------------\n```yaml\nNo birthdays found!\n```"
    else:
        # Sort upcoming
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

        sorted_birthdays = sorted(birthdays, key=upcoming_sort_key)
        pages = paginate_birthdays(sorted_birthdays, MAX_PINNED_ENTRIES)
        total_pages = len(pages)
        first_page = pages[0]

        content = build_pinned_page(first_page, guild, highlight_today=highlight_today, current_page=0, total_pages=total_pages, check_hour=check_hour)

    pinned_msg = None

    # --- Fetch stored pinned message from DB ---
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM config WHERE key=?", (f"pinned_birthday_msg_{guild.id}",)) as cursor:
            result = await cursor.fetchone()

        if result:
            try:
                pinned_msg_id = int(result[0])
                pinned_msg = await channel.fetch_message(pinned_msg_id)
            except discord.NotFound:
                pinned_msg = None
            except Exception as e:
                logger.warning(f"Error fetching pinned message in {guild.name}: {e}")
                pinned_msg = None

        if pinned_msg:
            try:
                await pinned_msg.edit(content=content)
            except Exception as e:
                logger.warning(f"Failed to edit pinned message in {guild.name}: {e}")
                pinned_msg = None

        if not pinned_msg:
            pinned_msg = await channel.send(content)
            if perms.manage_messages:
                try:
                    await pinned_msg.pin()
                except Exception as e:
                    logger.warning(f"Cannot pin message in {guild.name}: {e}")

            await db.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (f"pinned_birthday_msg_{guild.id}", str(pinned_msg.id))
            )
            await db.commit()

    return pinned_msg
