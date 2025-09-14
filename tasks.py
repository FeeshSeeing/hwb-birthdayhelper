import asyncio
import discord
import datetime as dt
from database import get_guild_config, get_birthdays
from utils import update_pinned_birthday_message, is_birthday_on_date # Import the new helper
from logger import logger # Import logger

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
        logger.warning(f"Birthday channel not found for guild {guild.name} ({guild_id}). Skipping check.")
        return

    now = today_override or dt.datetime.now(dt.timezone.utc)
    # The helper `is_birthday_on_date` will handle the day/month comparison, no need for today_str here.
    # today_str = now.strftime("%m-%d") # No longer needed directly for comparison

    if guild_id not in already_wished_today:
        already_wished_today[guild_id] = set()

    birthdays = await get_birthdays(guild_id)
    todays_birthdays = []

    for user_id, birthday in birthdays:
        # Use the consistent helper function
        if is_birthday_on_date(birthday, now) and (ignore_wished or user_id not in already_wished_today[guild_id]):
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
                            logger.warning(f"Cannot add birthday role to {member.mention} in {guild.name}. Permissions issue?")
                            await channel.send(f"⚠️ Cannot add birthday role to {member.mention}. Please check bot permissions and role hierarchy.", delete_after=10) # Added user-facing warning
                        except Exception as e:
                            logger.error(f"Error adding birthday role to {member.mention} in {guild.name}: {e}")
                            await channel.send(f"🚨 Error adding birthday role to {member.mention}. Please try again later.", delete_after=10)
            if not ignore_wished:
                already_wished_today[guild_id].add(user_id)

    try:
        await update_pinned_birthday_message(
            guild,
            highlight_today=todays_birthdays if todays_birthdays else None
        )
    except Exception as e:
        logger.warning(f"Could not refresh pinned message for {guild.name}: {e}") # Changed print to logger


async def remove_birthday_roles(guild: discord.Guild):
    config = await get_guild_config(str(guild.id))
    if not config or not config.get("birthday_role_id"):
        return

    role = guild.get_role(config["birthday_role_id"])
    if not role:
        logger.warning(f"Birthday role configured ({config['birthday_role_id']}) but not found in guild {guild.name}. Skipping role removal.")
        return

    for member in guild.members:
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Birthday day ended")
            except discord.Forbidden:
                logger.warning(f"Cannot remove birthday role from {member.display_name} in {guild.name}. Permissions issue?")
            except Exception as e:
                logger.error(f"Error removing birthday role from {member.display_name} in {guild.name}: {e}")


async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 60):
    global already_wished_today, last_checked_date

    while True:
        now = dt.datetime.now(dt.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        if last_checked_date != today_str:
            # New day
            logger.info(f"New day detected: {today_str}. Resetting birthday wishes and removing roles.")
            for guild in bot.guilds:
                if guild is None:
                    continue # Should not happen, but a safeguard
                await remove_birthday_roles(guild)

            already_wished_today = {}
            last_checked_date = today_str

            for guild in bot.guilds:
                if guild is None:
                    continue # Safeguard
                try:
                    # Compute today's birthdays to preserve confetti on first run
                    birthdays = await get_birthdays(str(guild.id))

                    # Use the consistent helper function here too
                    birthdays_today = [
                        user_id for user_id, birthday in birthdays
                        if is_birthday_on_date(birthday, now)
                    ]
                    await update_pinned_birthday_message(guild, highlight_today=birthdays_today)
                except Exception as e:
                    logger.warning(f"Could not refresh pinned message for {guild.name} on new day reset: {e}") # Changed print to logger

        for guild in bot.guilds:
            if guild is None:
                continue # Safeguard
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