import asyncio
import discord
import datetime as dt
from database import get_guild_config, get_birthdays
from utils import update_pinned_birthday_message  # <-- ADDED

already_wished_today = {}
last_checked_date = None  # track last day to reset

async def check_and_send_birthdays(
    guild: discord.Guild,
    today_override: dt.datetime = None,
    ignore_wished: bool = False
):
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

    if guild_id not in already_wished_today:
        already_wished_today[guild_id] = set()

    birthdays = await get_birthdays(guild_id)
    birthday_triggered = False  # track if any birthday triggered (for pinned refresh)

    for user_id, birthday in birthdays:
        b_month, b_day = map(int, birthday.split("-"))

        # Feb 29 handling
        if b_month == 2 and b_day == 29:
            is_leap = (now.year % 4 == 0 and (now.year % 100 != 0 or now.year % 400 == 0))
            if not is_leap:
                # Non-leap year: birthday effectively on Feb 28
                if today_override:
                    birthday_today = today_str in ["02-28", "02-29"]
                else:
                    birthday_today = today_str == "02-28"
            else:
                birthday_today = today_str == "02-29"
        else:
            birthday_today = today_str == birthday

        if birthday_today and (ignore_wished or user_id not in already_wished_today[guild_id]):
            birthday_triggered = True
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
                            await channel.send(
                                f"⚠️ Cannot add birthday role to {member.mention}."
                            )
            if not ignore_wished:
                already_wished_today[guild_id].add(user_id)

    # ✅ Refresh pinned birthday list if we sent any wishes
    if birthday_triggered:
        try:
            await update_pinned_birthday_message(guild)
        except Exception as e:
            print(f"[WARN] Could not refresh pinned message for {guild.name}: {e}")

async def remove_birthday_roles(guild: discord.Guild):
    """Remove birthday role from all members at the start of a new day."""
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
                pass  # ignore if bot lacks permissions

async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 60):
    """Background loop to check birthdays every interval_minutes (GMT+0)."""
    global already_wished_today, last_checked_date

    while True:
        now = dt.datetime.now(dt.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        if last_checked_date != today_str:
            # 1️⃣ Remove birthday roles first
            for guild in bot.guilds:
                await remove_birthday_roles(guild)

            # 2️⃣ Reset tracking
            already_wished_today = {}
            last_checked_date = today_str

        for guild in bot.guilds:
            await check_and_send_birthdays(guild)

        await asyncio.sleep(interval_minutes * 60)

async def run_birthday_check_once(
    bot: discord.Client,
    guild: discord.Guild = None,
    test_date: dt.datetime = None
):
    """Run birthday check once for a specific guild or all guilds."""
    if guild:
        await check_and_send_birthdays(guild, today_override=test_date, ignore_wished=True)
    else:
        for g in bot.guilds:
            await check_and_send_birthdays(g, today_override=test_date, ignore_wished=True)
