import calendar
import aiosqlite
import discord
import datetime as dt
from config import DB_FILE
from database import get_birthdays, get_guild_config
from logger import logger

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
    """Checks if a given birthday string matches a specific date, handling Feb 29 leap year logic."""
    b_month, b_day = map(int, birthday_str.split("-"))

    if b_month == 2 and b_day == 29:
        is_leap_year = (check_date.year % 4 == 0 and (check_date.year % 100 != 0 or check_date.year % 400 == 0))
        return (check_date.month == 2 and check_date.day == 29 and is_leap_year) or \
               (check_date.month == 2 and check_date.day == 28 and not is_leap_year)
    else:
        return check_date.month == b_month and check_date.day == b_day

async def update_pinned_birthday_message(
    guild: discord.Guild,
    highlight_today: list[str] = None,
    manual: bool = False
):
    guild_config = await get_guild_config(str(guild.id))
    if not guild_config:
        logger.warning(f"No guild config for {guild.name}, skipping pinned message update.")
        return

    # Convert channel ID to int
    try:
        channel_id = int(guild_config["channel_id"])
    except (TypeError, ValueError):
        logger.error(f"Invalid channel ID in guild config for {guild.name}: {guild_config['channel_id']}")
        return

    channel = guild.get_channel(channel_id)
    if not channel:
        logger.warning(f"Birthday channel not found for guild {guild.name} (ID: {guild.id}). Skipping check.")
        return

    # Get daily check hour, default 9 UTC
    check_hour = guild_config.get("check_hour", 9)

    birthdays = await get_birthdays(str(guild.id))
    if not birthdays:
        content = "📂 No birthdays found yet."
    else:
        today = dt.datetime.now(dt.timezone.utc)

        def upcoming_sort_key(b):
            month, day = map(int, b[1].split("-"))
            
            # Adjust day for Feb 29 in non-leap years
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

        sorted_birthdays = sorted(birthdays, key=lambda x: upcoming_sort_key(x))
        lines = ["**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**"]
        for idx, (user_id, birthday) in enumerate(sorted_birthdays):
            if idx >= MAX_PINNED_ENTRIES:
                break
            member = guild.get_member(int(user_id))
            name = member.display_name if member else f"<@{user_id}>"
            if highlight_today and user_id in highlight_today:
                name = f"{CONFETTI_ICON} {name}"
            lines.append(f"✦ {name}: {format_birthday_display(birthday)}")

        if len(sorted_birthdays) > MAX_PINNED_ENTRIES:
            lines.append(
                f"\n⚠️ {len(sorted_birthdays) - MAX_PINNED_ENTRIES} more birthdays not shown.\nUse /viewbirthdays to view the full list."
            )

        lines.append("\n> *💡 Tip: Use /setbirthday to add your own special day!*")
        lines.append(f"_Bot checks birthdays daily at {check_hour}:00 UTC_")

        content = "\n".join(lines)

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT value FROM config WHERE key=?", (f"pinned_birthday_msg_{guild.id}",)
        ) as cursor:
            result = await cursor.fetchone()
        pinned_msg = None
        
        if result:
            pinned_msg_id = int(result[0])
            try:
                pinned_msg = await channel.fetch_message(pinned_msg_id)
                logger.debug(f"Successfully fetched existing pinned message {pinned_msg_id} for guild {guild.name}.")
            except discord.NotFound:
                logger.warning(f"Pinned message (ID: {pinned_msg_id}) not found in guild {guild.name}. Creating a new one.")
                pinned_msg = None
            except discord.Forbidden:
                logger.error(f"Bot lacks permissions to fetch pinned message (ID: {pinned_msg_id}) in guild {guild.name}. Creating a new one.")
                pinned_msg = None
            except Exception as e:
                logger.error(f"Error fetching pinned message (ID: {pinned_msg_id}) in guild {guild.name}: {e}. Creating a new one.", exc_info=True)
                pinned_msg = None

        if pinned_msg:
            try:
                await pinned_msg.edit(content=content)
                logger.info(f"Edited existing pinned birthday message (ID: {pinned_msg.id}) for guild {guild.name}.")
            except discord.NotFound:
                logger.warning(f"Pinned message (ID: {pinned_msg.id}) disappeared before edit in guild {guild.name}. Creating a new one.")
                pinned_msg = None
            except discord.Forbidden:
                logger.error(f"Bot lacks permissions to edit pinned message (ID: {pinned_msg.id}) in guild {guild.name}. Creating a new one.")
                pinned_msg = None
            except Exception as e:
                logger.error(f"Error editing pinned message (ID: {pinned_msg.id}) in guild {guild.name}: {e}. Creating a new one.", exc_info=True)
                pinned_msg = None
        
        if not pinned_msg:
            try:
                pinned_msg = await channel.send(content)
                logger.info(f"Created new pinned birthday message (ID: {pinned_msg.id}) for guild {guild.name}.")
                if channel.permissions_for(guild.me).manage_messages:
                    try:
                        await pinned_msg.pin()
                        logger.info(f"Pinned new birthday message (ID: {pinned_msg.id}) for guild {guild.name}.")
                    except discord.Forbidden:
                        logger.warning(f"Bot lacks permissions to pin message in channel {channel.name} ({channel.id}) in guild {guild.name}.")
                else:
                    logger.warning(f"Bot lacks 'Manage Messages' permission to pin message in channel {channel.name} ({channel.id}) in guild {guild.name}.")
            except discord.Forbidden:
                logger.error(f"Bot lacks permissions to send messages in channel {channel.name} ({channel.id}) in guild {guild.name}. Cannot create or pin.")
                return
            except Exception as e:
                logger.error(f"Error sending new pinned message in channel {channel.name} ({channel.id}) in guild {guild.name}: {e}.", exc_info=True)
                return

        if pinned_msg:
            await db.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (f"pinned_birthday_msg_{guild.id}", str(pinned_msg.id))
            )
            await db.commit()
            logger.debug(f"📌 Pinned birthday message ID {pinned_msg.id} updated/stored for guild {guild.name}")
