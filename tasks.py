import asyncio
import discord
import datetime as dt
from database import get_guild_config, get_birthdays

already_wished_today = {}
last_checked_date = None  # track last day to reset

async def check_and_send_birthdays(guild: discord.Guild, today_override: dt.datetime = None):
    """Check birthdays for a guild and send messages if today matches (GMT+0)."""
    global already_wished_today

    guild_id = str(guild.id)
    config = await get_guild_config(guild_id)
    if not config:
        return

    channel = guild.get_channel(config["channel_id"])
    if not channel:
        return

    now = today_override or dt.datetime.now(dt.timezone.utc)
    today_str = now.strftime("%m-%d")
    today_month, today_day = now.month, now.day

    if guild_id not in already_wished_today:
        already_wished_today[guild_id] = set()

    birthdays = await get_birthdays(guild_id)
    for user_id, birthday in birthdays:
        b_month, b_day = map(int, birthday.split("-"))

        # Feb 29 handling
        if b_month == 2 and b_day == 29:
            is_leap = (now.year % 4 == 0 and (now.year % 100 != 0 or now.year % 400 == 0))
            birthday_today = (today_str == "02-29") if is_leap else (today_str == "02-28")
        else:
            birthday_today = today_str == birthday

        if birthday_today and user_id not in already_wished_today[guild_id]:
            member = guild.get_member(int(user_id))
            if member:
                await channel.send(
                    f"Happy Birthday, {member.mention}! 🎈\n"
                    f"From all of us at {guild.name}, sending you lots of love today 💖🎂"
                )
                # Add birthday role if configured
                if config.get("birthday_role_id"):
                    role = guild.get_role(config["birthday_role_id"])
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="Birthday!")
                        except discord.Forbidden:
                            await channel.send(f"⚠️ Cannot add birthday role to {member.mention}.")
            already_wished_today[guild_id].add(user_id)

async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 60):
    """Background loop to check birthdays every interval_minutes (GMT+0)."""
    global already_wished_today, last_checked_date

    while True:
        now = dt.datetime.now(dt.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        if last_checked_date != today_str:
            already_wished_today = {}
            last_checked_date = today_str

        for guild in bot.guilds:
            await check_and_send_birthdays(guild)

        await asyncio.sleep(interval_minutes * 60)

async def run_birthday_check_once(bot: discord.Client, test_date: dt.datetime = None):
    """Run birthday check once for all guilds. Optional test_date overrides today."""
    for guild in bot.guilds:
        await check_and_send_birthdays(guild, today_override=test_date)
