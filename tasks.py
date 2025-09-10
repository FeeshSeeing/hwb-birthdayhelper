# tasks.py
import asyncio
import datetime
import discord
from database import get_guild_config, get_birthdays  # your db helpers

# Track users already wished per guild
already_wished_today = {}
last_checked_date = None  # track last day to reset

async def check_and_send_birthdays(guild: discord.Guild):
    """Check birthdays for a guild and send messages if today matches."""
    global already_wished_today

    guild_id = str(guild.id)
    config = await get_guild_config(guild_id)
    if not config:
        return
    channel = guild.get_channel(config["channel_id"])
    if not channel:
        return

    now = datetime.datetime.now()
    today_str = now.strftime("%m-%d")

    if guild_id not in already_wished_today:
        already_wished_today[guild_id] = set()

    birthdays = await get_birthdays(guild_id)
    for user_id, birthday in birthdays:
        if birthday == today_str and user_id not in already_wished_today[guild_id]:
            member = guild.get_member(int(user_id))
            if member:
                await channel.send(
                    f"Happy Birthday, {member.mention}! 🎈\n"
                    f"From all of us at {guild.name}, sending you lots of love today 💖🎂"
                )
                # Add role if configured
                if config["birthday_role_id"]:
                    role = guild.get_role(config["birthday_role_id"])
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="Birthday!")
                        except discord.Forbidden:
                            await channel.send(f"⚠️ Cannot add birthday role to {member.mention}.")
            already_wished_today[guild_id].add(user_id)

async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 60):
    """Background loop to check birthdays every interval_minutes."""
    global already_wished_today, last_checked_date

    while True:
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        if last_checked_date != today_str:
            already_wished_today = {}
            last_checked_date = today_str

        for guild in bot.guilds:
            try:
                await check_and_send_birthdays(guild)
            except Exception as e:
                from logger import logger
                logger.error(f"Error checking birthdays for {guild.name}: {e}")

        await asyncio.sleep(interval_minutes * 60)

# Optional helper to run manually from /testbirthday
async def run_birthday_check_once(bot: discord.Client):
    """Run birthday check once for all guilds (for /testbirthday)."""
    for guild in bot.guilds:
        await check_and_send_birthdays(guild)
