# tasks.py
import asyncio
from datetime import datetime, timezone
import discord
from database import get_guild_config, get_birthdays

# Track users already wished per guild
already_wished_today = {}
last_checked_date = None  # track last day to reset


async def check_and_send_birthdays(guild: discord.Guild, test_date: datetime = None):
    """Check birthdays for a guild and send messages if today matches (GMT+0)."""
    global already_wished_today

    guild_id = str(guild.id)
    config = await get_guild_config(guild_id)
    if not config:
        return

    channel = guild.get_channel(config["channel_id"])
    if not channel:
        return

    # Use test_date if provided (for /testdate), else use current UTC
    now = test_date or datetime.now(timezone.utc)
    today_str = now.strftime("%m-%d")
    today_month, today_day = now.month, now.day

    if guild_id not in already_wished_today:
        already_wished_today[guild_id] = set()

    birthdays = await get_birthdays(guild_id)
    birthday_role = guild.get_role(config.get("birthday_role_id")) if config.get("birthday_role_id") else None

    for user_id, birthday in birthdays:
        b_month, b_day = map(int, birthday.split("-"))

        # Handle Feb 29 birthdays on non-leap years as Feb 28
        if b_month == 2 and b_day == 29:
            is_leap = (now.year % 4 == 0 and (now.year % 100 != 0 or now.year % 400 == 0))
            birthday_today = (today_str == "02-29") if is_leap else (today_str == "02-28")
        else:
            birthday_today = today_str == birthday

        member = guild.get_member(int(user_id))
        if not member:
            continue

        if birthday_today and user_id not in already_wished_today[guild_id]:
            # Send birthday message
            await channel.send(
                f"Happy Birthday, {member.mention}! 🎈\n"
                f"From all of us at {guild.name}, sending you lots of love today 💖🎂"
            )

            # Add birthday role if configured
            if birthday_role and birthday_role not in member.roles:
                try:
                    await member.add_roles(birthday_role, reason="Birthday!")
                except discord.Forbidden:
                    await channel.send(f"⚠️ Cannot add birthday role to {member.mention}.")

            already_wished_today[guild_id].add(user_id)
        elif birthday_role and birthday_role in member.roles and not birthday_today:
            # Remove birthday role if it’s not their birthday today
            try:
                await member.remove_roles(birthday_role, reason="Birthday finished")
            except discord.Forbidden:
                await channel.send(f"⚠️ Cannot remove birthday role from {member.mention}.")


async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 60):
    """Background loop to check birthdays every interval_minutes (GMT+0)."""
    global already_wished_today, last_checked_date

    while True:
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        # Reset daily tracking at midnight GMT+0
        if last_checked_date != today_str:
            already_wished_today = {}
            last_checked_date = today_str

        for guild in bot.guilds:
            await check_and_send_birthdays(guild)

        await asyncio.sleep(interval_minutes * 60)


# Optional helper to run manually (used by /testdate)
async def run_birthday_check_once(bot: discord.Client, test_date: datetime = None):
    """Run birthday check once for all guilds."""
    for guild in bot.guilds:
        await check_and_send_birthdays(guild, test_date=test_date)
