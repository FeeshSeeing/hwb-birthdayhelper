import asyncio
import discord
import datetime as dt
from database import get_guild_config, get_birthdays
from utils import update_pinned_birthday_message

already_wished_today = {}
last_checked_date = None  # Track last day to reset

async def check_and_send_birthdays(
    guild: discord.Guild,
    today_override: dt.datetime = None,
    ignore_wished: bool = False
):
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

    if guild_id not in already_wished_today:
        already_wished_today[guild_id] = set()

    birthdays = await get_birthdays(guild_id)
    todays_birthdays = []

    for user_id, birthday in birthdays:
        b_month, b_day = map(int, birthday.split("-"))

        # Feb 29 handling
        if b_month == 2 and b_day == 29:
            is_leap = (now.year % 4 == 0 and (now.year % 100 != 0 or now.year % 400 == 0))
            birthday_today = today_str == ("02-29" if is_leap else "02-28")
        else:
            birthday_today = today_str == birthday

        if birthday_today and (ignore_wished or user_id not in already_wished_today[guild_id]):
            todays_birthdays.append(user_id)
            member = guild.get_member(int(user_id))
            if member:
                await channel.send(
                    f"Happy Birthday, {member.mention}! 🎈\n"
                    f"From all of us at {guild.name}, sending you lots of love today 💖🎂"
                )
                if config.get("birthday_role_id"):
                    role = guild.get_role(config["birthday_role_id"])
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="Birthday!")
                        except discord.Forbidden:
                            await channel.send(f"⚠️ Cannot add birthday role to {member.mention}.")
            if not ignore_wished:
                already_wished_today[guild_id].add(user_id)

    try:
        await update_pinned_birthday_message(
            guild,
            highlight_today=todays_birthdays if todays_birthdays else None
        )
    except Exception as e:
        print(f"[WARN] Could not refresh pinned message for {guild.name}: {e}")

async def remove_birthday_roles(guild: discord.Guild):
    config = await get_guild_config(str(guild.id))
    if not config or not config.get("birthday_role_id"):
        return

    role = guild.get_role(config["birthday_role_id"])
    if not role:
        return

    for member in guild.members:
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Birthday day ended")
            except discord.Forbidden:
                pass

async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 60):
    global already_wished_today, last_checked_date

    while True:
        now = dt.datetime.now(dt.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        if last_checked_date != today_str:
            # Start of a new day
            for guild in bot.guilds:
                await remove_birthday_roles(guild)

            already_wished_today = {}
            last_checked_date = today_str

            for guild in bot.guilds:
                try:
                    await update_pinned_birthday_message(guild)
                except Exception as e:
                    print(f"[WARN] Could not refresh pinned message for {guild.name}: {e}")

        for guild in bot.guilds:
            await check_and_send_birthdays(guild)

        await asyncio.sleep(interval_minutes * 60)

async def run_birthday_check_once(
    bot: discord.Client,
    guild: discord.Guild = None,
    test_date: dt.datetime = None
):
    if guild:
        await check_and_send_birthdays(guild, today_override=test_date, ignore_wished=True)
    else:
        for g in bot.guilds:
            await check_and_send_birthdays(g, today_override=test_date, ignore_wished=True)
