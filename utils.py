import calendar
import aiosqlite
import discord
import datetime as dt
from config import DB_FILE
from database import get_birthdays, get_guild_config
from logger import logger

MAX_PINNED_ENTRIES = 3  # Show first 20 in pinned message
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


async def update_pinned_birthday_message(
    guild: discord.Guild,
    highlight_today: list[str] = None,
    manual: bool = False
) -> discord.Message | None:
    """Update (or create if missing) the pinned birthday message for this guild."""

    guild_config = await get_guild_config(str(guild.id))
    if not guild_config:
        logger.warning(f"No guild config for {guild.name}, skipping pinned message update.")
        return None

    # --- Resolve channel ---
    try:
        channel_id = int(guild_config["channel_id"])
    except (TypeError, ValueError):
        logger.error(f"Invalid channel ID in guild config for {guild.name}: {guild_config.get('channel_id')}")
        return None

    channel = guild.get_channel(channel_id)
    if not channel:
        try:
            channel = await guild.fetch_channel(channel_id)
        except discord.NotFound:
            logger.warning(f"Birthday channel not found for guild {guild.name} (ID: {channel_id}).")
            return None
        except discord.Forbidden:
            logger.error(f"Cannot access channel {channel_id} in guild {guild.name}. Missing permissions.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching channel {channel_id} in {guild.name}: {e}")
            return None

    perms = channel.permissions_for(guild.me)
    if not perms.send_messages:
        logger.error(f"Bot cannot send messages in channel {channel.name} ({channel.id}) in guild {guild.name}.")
        return None

    # --- Build message content ---
    check_hour = guild_config.get("check_hour", 9)
    birthdays = await get_birthdays(str(guild.id))
    today = dt.datetime.now(dt.timezone.utc)

    if not birthdays:
        content = "🎂 BIRTHDAY LIST 🎂\n------------------------\n```yaml\nNo birthdays found!\n```"
    else:
        # Sort upcoming birthdays
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

        # Prepare aligned layout
        entries = []
        for user_id, birthday in sorted_birthdays[:MAX_PINNED_ENTRIES]:
            member = guild.get_member(int(user_id))
            name = member.display_name if member else f"<@{user_id}>"
            if highlight_today and str(user_id) in map(str, highlight_today):
                name = f"{CONFETTI_ICON} {name}"
            entries.append((name, format_birthday_display(birthday)))

        max_name_len = max(len(name) for name, _ in entries) if entries else 0

        formatted_lines = []
        for name, date in entries:
            dots = "·" * (max_name_len - len(name) + 5)
            formatted_lines.append(f"・{name} {dots} {date}")

        content = (
            "🎂 BIRTHDAY LIST 🎂\n"
            "------------------------\n"
            "```yaml\n" +
            "\n".join(formatted_lines) +
            "\n```"
        )

        if len(sorted_birthdays) > MAX_PINNED_ENTRIES:
            content += (
                f"\n⚠️ {len(sorted_birthdays) - MAX_PINNED_ENTRIES} more birthdays not shown.\n"
                "Use /viewbirthdays to view the full list."
            )

        content += f"\n> *💡 Tip: Use /setbirthday to add your own special day!*\n> *Bot checks birthdays daily at {check_hour}:00 UTC*"

    pinned_msg = None

    # --- Fetch stored pinned message from DB ---
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT value FROM config WHERE key=?", (f"pinned_birthday_msg_{guild.id}",)
        ) as cursor:
            result = await cursor.fetchone()

        if result:
            try:
                pinned_msg_id = int(result[0])
                pinned_msg = await channel.fetch_message(pinned_msg_id)
            except discord.NotFound:
                logger.info(f"Stored pinned message not found in {guild.name}, will create new one.")
                pinned_msg = None
            except Exception as e:
                logger.warning(f"Error fetching pinned message in {guild.name}: {e}")
                pinned_msg = None

        if pinned_msg:
            try:
                await pinned_msg.edit(content=content)
                logger.info(f"Edited pinned birthday message (ID: {pinned_msg.id}) for guild {guild.name}.")
            except Exception as e:
                logger.warning(f"Failed to edit pinned message in {guild.name}: {e}")
                pinned_msg = None  # fallback to create new message

        if not pinned_msg:
            pinned_msg = await channel.send(content)
            logger.info(f"Created new birthday message (ID: {pinned_msg.id}) for guild {guild.name}.")
            if perms.manage_messages:
                try:
                    await pinned_msg.pin()
                    logger.info(f"Pinned new birthday message (ID: {pinned_msg.id}) for guild {guild.name}.")
                except discord.Forbidden:
                    logger.warning(f"Cannot pin message in {guild.name}, missing permission.")
                except Exception as e:
                    logger.warning(f"Unexpected error pinning message in {guild.name}: {e}")

            await db.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (f"pinned_birthday_msg_{guild.id}", str(pinned_msg.id))
            )
            await db.commit()
            logger.debug(f"Stored pinned birthday message ID {pinned_msg.id} for guild {guild.name}")

    return pinned_msg
