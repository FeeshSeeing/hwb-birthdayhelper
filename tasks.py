import asyncio
import discord
import datetime as dt
import aiosqlite
from database import get_guild_config, get_birthdays
from utils import update_pinned_birthday_message, is_birthday_on_date
from logger import logger

DB_FILE = "birthdays.db"

# -------------------- Wished Table --------------------
async def ensure_wished_table():
    """Create wished_today table if it doesn't exist."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS wished_today (
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id, date)
        )
        """)
        await db.commit()

async def has_been_wished(guild_id: str, user_id: str, date_str: str) -> bool:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT 1 FROM wished_today WHERE guild_id = ? AND user_id = ? AND date = ?",
            (guild_id, user_id, date_str)
        ) as cursor:
            return await cursor.fetchone() is not None

async def mark_as_wished(guild_id: str, user_id: str, date_str: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO wished_today (guild_id, user_id, date) VALUES (?, ?, ?)",
            (guild_id, user_id, date_str)
        )
        await db.commit()

async def clear_old_wishes(date_str: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM wished_today WHERE date != ?", (date_str,))
        await db.commit()
        logger.info("🧹 Cleared old wished_today entries.")

# -------------------- Birthday Check --------------------
async def check_and_send_birthdays(
    guild: discord.Guild,
    today_override: dt.datetime = None,
    ignore_wished: bool = False
):
    guild_id = str(guild.id)
    config = await get_guild_config(guild_id)
    if not config:
        logger.debug(f"No config found in DB for guild {guild.name} ({guild.id})")
        return

    # --- Channel Handling ---
    channel_id = config.get("channel_id")
    channel = guild.get_channel(channel_id)
    if channel:
        logger.info(f"Using birthday channel: {channel.name} ({channel.id}) in {guild.name}")
    else:
        visible_channels = [(c.name, c.id) for c in guild.channels]
        logger.warning(
            f"Birthday channel {channel_id} not found in guild {guild.name} ({guild.id}). "
            f"Visible channels: {visible_channels}"
        )
        return

    # --- Role Handling ---
    role_id = config.get("birthday_role_id")
    role = guild.get_role(role_id) if role_id else None
    if role:
        logger.info(f"Using birthday role: {role.name} ({role.id}) in {guild.name}")
    else:
        if role_id:
            visible_roles = [(r.name, r.id) for r in guild.roles]
            logger.warning(
                f"Birthday role {role_id} not found in guild {guild.name} ({guild.id}). "
                f"Visible roles: {visible_roles}"
            )

    now = today_override or dt.datetime.now(dt.timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    birthdays = await get_birthdays(guild_id)
    todays_birthdays = []

    logger.debug(f"Checking birthdays in {guild.name} for {now.strftime('%d/%m/%Y')} (UTC). "
                 f"Found {len(birthdays)} entries in DB.")

    for user_id, birthday in birthdays:
        if is_birthday_on_date(birthday, now):
            if not ignore_wished and await has_been_wished(guild_id, user_id, date_str):
                logger.debug(f"Skipping {user_id} in {guild.name} (already wished today).")
                continue

            todays_birthdays.append(user_id)
            member = guild.get_member(int(user_id))
            if member:
                try:
                    await channel.send(
                        f"🎉 Happy Birthday, {member.mention}! 🎈\n"
                        f"From all of us at **{guild.name}**, sending you lots of love today 💖🎂"
                    )
                    logger.info(f"Sent birthday message for {member.display_name} in {guild.name}")
                except Exception as e:
                    logger.error(f"Failed to send birthday message in {guild.name}: {e}")

                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Birthday!")
                        logger.info(f"Added birthday role to {member.display_name} in {guild.name}")
                    except discord.Forbidden:
                        logger.warning(f"Cannot add birthday role to {member.display_name} in {guild.name} "
                                       f"(Permissions issue / role hierarchy).")
                        await channel.send(
                            f"⚠️ Cannot add birthday role to {member.mention}. Check bot permissions and role hierarchy.",
                            delete_after=10
                        )
                    except Exception as e:
                        logger.error(f"Error adding birthday role to {member.display_name} in {guild.name}: {e}")
                        await channel.send(
                            f"🚨 Error adding birthday role to {member.mention}. Try again later.",
                            delete_after=10
                        )

            if not ignore_wished:
                await mark_as_wished(guild_id, user_id, date_str)

    # --- Update Pinned Message ---
    try:
        await update_pinned_birthday_message(
            guild,
            highlight_today=todays_birthdays if todays_birthdays else None
        )
    except Exception as e:
        logger.warning(f"Could not refresh pinned message for {guild.name}: {e}")

# -------------------- Remove Birthday Roles --------------------
async def remove_birthday_roles(guild: discord.Guild):
    config = await get_guild_config(str(guild.id))
    if not config or not config.get("birthday_role_id"):
        return

    role_id = config.get("birthday_role_id")
    role = guild.get_role(role_id)
    if not role:
        logger.warning(f"Birthday role {role_id} not found in guild {guild.name}. Skipping role removal.")
        return

    for member in guild.members:
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Birthday day ended")
                logger.debug(f"Removed birthday role from {member.display_name} in {guild.name}")
            except discord.Forbidden:
                logger.warning(f"Cannot remove birthday role from {member.display_name} in {guild.name}. Permissions issue?")
            except Exception as e:
                logger.error(f"Error removing birthday role from {member.display_name} in {guild.name}: {e}")

# -------------------- Birthday Check Loop --------------------
async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 60):
    await ensure_wished_table()

    # --- Catch-up on startup ---
    now = dt.datetime.now(dt.timezone.utc)
    logger.info("🟢 Running initial birthday check (catch-up) for all guilds")
    for guild in bot.guilds:
        if guild:
            await check_and_send_birthdays(guild, ignore_wished=True)

    # --- Main Loop ---
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        current_hour = now.hour
        today_str = now.strftime("%Y-%m-%d")

        logger.debug(f"Running birthday loop for {today_str} (UTC hour {current_hour})")
        await clear_old_wishes(today_str)

        for guild in bot.guilds:
            if guild:
                config = await get_guild_config(str(guild.id))
                check_hour = config.get("check_hour") if config else None
                if check_hour is None:
                    logger.debug(f"No check_hour set for guild {guild.name}, skipping timed check.")
                    continue

                if current_hour == int(check_hour):
                    await remove_birthday_roles(guild)
                    await check_and_send_birthdays(guild)
                else:
                    logger.debug(f"Skipping guild {guild.name}, current hour {current_hour} != check_hour {check_hour}")

        await asyncio.sleep(interval_minutes * 60)

# -------------------- Run Once for Test --------------------
async def run_birthday_check_once(
    bot: discord.Client,
    guild: discord.Guild = None,
    test_date: dt.datetime = None
):
    await ensure_wished_table()

    if guild:
        await remove_birthday_roles(guild)
        await check_and_send_birthdays(guild, today_override=test_date, ignore_wished=True)
    else:
        for g in bot.guilds:
            await remove_birthday_roles(g)
            await check_and_send_birthdays(g, today_override=test_date, ignore_wished=True)
