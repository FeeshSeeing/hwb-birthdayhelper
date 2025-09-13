import calendar
import aiosqlite
import discord
import datetime as dt
from database import DB_FILE, get_birthdays, get_guild_config
from logger import logger

MAX_PINNED_ENTRIES = 20  # Show only first 20 in pinned message

def parse_day_month_input(day_input, month_input):
    """Validate and parse day and month input."""
    try:
        day = int(day_input)
        month = int(month_input)
        if 1 <= day <= 31 and 1 <= month <= 12:
            return day, month
    except ValueError:
        pass
    return None

def format_birthday_display(birthday_str):
    """Return human-readable string like '25th December'."""
    try:
        month_str, day_str = birthday_str.split("-")
        month, day = int(month_str), int(day_str)
        month_name = calendar.month_name[month]
        if 4 <= day <= 20 or 24 <= day <= 30:
            suffix = "th"
        else:
            suffixes = ["st", "nd", "rd"]
            suffix = suffixes[(day % 10) - 1] if 1 <= day % 10 <= 3 else "th"
        return f"{day}{suffix} {month_name}"
    except:
        return birthday_str

async def update_pinned_birthday_message(guild: discord.Guild, highlight_today: list[str] = None):
    """Update pinned message for the server with all birthdays sorted by upcoming date.
    Optionally highlight today's birthdays and move them to the bottom.
    """
    guild_config = await get_guild_config(str(guild.id))
    if not guild_config:
        logger.warning(f"No guild config for {guild.name}, skipping pinned message update.")
        return

    channel = guild.get_channel(guild_config["channel_id"])
    if not channel:
        logger.warning(f"Channel not found for pinned message in guild {guild.name}")
        return

    birthdays = await get_birthdays(str(guild.id))
    if not birthdays:
        content = "📂 No birthdays found yet."
    else:
        today = dt.datetime.now(dt.timezone.utc)
        today_month, today_day = today.month, today.day

        def upcoming_sort_key(birthday_str):
            month, day = map(int, birthday_str.split("-"))
            # Handle Feb 29 birthdays on non-leap years as Feb 28
            if month == 2 and day == 29:
                is_leap = (today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0))
                if not is_leap:
                    day = 28
            delta = (month - today_month) * 31 + (day - today_day)
            return delta if delta >= 0 else delta + 12 * 31  # wrap around year

        # Sort birthdays based on upcoming date from today
        sorted_birthdays = sorted(birthdays, key=lambda x: upcoming_sort_key(x[1]))

        # ✅ Highlight today's birthdays and move them to bottom
        if highlight_today:
            sorted_birthdays = (
                [b for b in sorted_birthdays if b[0] not in highlight_today]
                + [b for b in sorted_birthdays if b[0] in highlight_today]
            )

        lines = ["**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**"]
        for idx, (user_id, birthday) in enumerate(sorted_birthdays):
            if idx >= MAX_PINNED_ENTRIES:
                break
            member = guild.get_member(int(user_id))
            name = member.display_name if member else f"<@{user_id}>"
            if highlight_today and user_id in highlight_today:
                name = f"🎉 {name}"
            lines.append(f"✦ {name}: {format_birthday_display(birthday)}")

        # Add note if more birthdays exist
        if len(sorted_birthdays) > MAX_PINNED_ENTRIES:
            lines.append(
                f"\n⚠️ {len(sorted_birthdays) - MAX_PINNED_ENTRIES} more birthdays not shown.\nUse /birthdaylist to view the full list with pages."
            )

        content = "\n".join(lines)

    # Fetch or create pinned message
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT value FROM config WHERE key=?", (f"pinned_birthday_msg_{guild.id}",)
        ) as cursor:
            result = await cursor.fetchone()
        pinned_msg = None
        if result:
            try:
                pinned_msg = await channel.fetch_message(int(result[0]))
            except discord.NotFound:
                pinned_msg = None

        if pinned_msg:
            await pinned_msg.edit(content=content)
        else:
            pinned_msg = await channel.send(content)
            if channel.permissions_for(guild.me).manage_messages:
                await pinned_msg.pin()

        await db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (f"pinned_birthday_msg_{guild.id}", str(pinned_msg.id))
        )
        await db.commit()
        logger.info(f"📌 Pinned birthday message updated in guild {guild.name}")
