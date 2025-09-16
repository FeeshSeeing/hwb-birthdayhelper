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
    logger.debug("Ensuring wished_today table exists in DB...")
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
    logger.debug("✅ wished_today table check complete.")

async def has_been_wished(guild_id: str, user_id: str, date_str: str) -> bool:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT 1 FROM wished_today WHERE guild_id = ? AND user_id = ? AND date = ?",
            (guild_id, user_id, date_str)
        ) as cursor:
            result = await cursor.fetchone()
            logger.debug(f"has_been_wished? guild={guild_id}, user={user_id}, date={date_str} -> {bool(result)}")
            return result is not None

async def mark_as_wished(guild_id: str, user_id: str, date_str: str):
    logger.debug(f"Marking user {user_id} as wished in guild {guild_id} for {date_str}")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO wished_today (guild_id, user_id, date) VALUES (?, ?, ?)",
            (guild_id, user_id, date_str)
        )
        await db.commit()

async def clear_old_wishes(retain_days: int = 7):
    """Delete entries older than retain_days (keeps today safe)."""
    today = dt.datetime.now(dt.timezone.utc)
    cutoff_date = (today - dt.timedelta(days=retain_days)).strftime("%Y-%m-%d")
    logger.info(f"🧹 Clearing wished_today entries older than {cutoff_date}")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM wished_today WHERE date < ?", (cutoff_date,))
        await db.commit()
    logger.debug("✅ Old wishes cleared.")

# -------------------- Birthday Check --------------------
already_logged_missing_roles_remove = set()  # global set
already_logged_missing_roles_add = set()     # global set

async def check_and_send_birthdays(guild: discord.Guild, today_override: dt.datetime = None, ignore_wished: bool = False):
    guild_name = guild.name
    guild_id = str(guild.id)
    logger.info(f"🔍 Checking birthdays for guild {guild_name}...")

    config = await get_guild_config(guild_id)
    if not config:
        logger.warning(f"❗ No config found for guild {guild_name} — skipping.")
        return

    # --- Resolve channel ---
    channel_id = config.get("channel_id")
    channel = guild.get_channel(int(channel_id)) if channel_id else None
    if not channel:
        try:
            channel = await guild.fetch_channel(int(channel_id))
            logger.info(f"✅ Fetched birthday channel {channel.name} for {guild_name}")
        except Exception as e:
            logger.warning(f"❌ Cannot find/access birthday channel {channel_id} in {guild_name}: {e}")
            return

    # --- Resolve role ---
    role_id = config.get("birthday_role_id")
    role = None
    if role_id:
        try:
            role_id_int = int(role_id)
            role = guild.get_role(role_id_int)
            if not role and guild.id not in already_logged_missing_roles_add:
                try:
                    role = await guild.fetch_role(role_id_int)
                    logger.info(f"✅ Fetched birthday role {role.name} via API for {guild_name}")
                except Exception as e:
                    logger.warning(f"❗ Cannot find/access birthday role {role_id_int} in {guild_name}: {e}")
                    already_logged_missing_roles_add.add(guild.id)
        except (TypeError, ValueError):
            logger.warning(f"❗ Invalid birthday role ID in {guild_name}, skipping role assignment.")

    now = today_override or dt.datetime.now(dt.timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    birthdays = await get_birthdays(guild_id)
    logger.info(f"📋 Found {len(birthdays)} birthday entries in DB for {guild_name}")
    todays_birthdays = []

    sent_this_loop = set()

    for user_id, birthday in birthdays:
        if user_id in sent_this_loop:
            continue

        if is_birthday_on_date(birthday, now):
            if not ignore_wished and await has_been_wished(guild_id, user_id, date_str):
                continue

            todays_birthdays.append(user_id)
            sent_this_loop.add(user_id)

            member = guild.get_member(int(user_id))
            if member:
                try:
                    await channel.send(
                        f"🎉 Happy Birthday, {member.mention}! 🎈\n"
                        f"From all of us at **{guild_name}**, sending you lots of love today 💖🎂"
                    )
                    logger.info(f"✅ Sent birthday message for {member.display_name} in {guild_name}")
                except Exception as e:
                    logger.error(f"❌ Failed to send birthday message for {member.display_name} in {guild_name}: {e}")

                if role and member and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Birthday!")
                        logger.info(f"✅ Added birthday role to {member.display_name} in {guild_name}")
                    except Exception as e:
                        logger.warning(f"❗ Could not add birthday role to {member.display_name}: {e}")

            if not ignore_wished:
                await mark_as_wished(guild_id, user_id, date_str)

    # Update pinned message
    try:
        await update_pinned_birthday_message(guild, highlight_today=todays_birthdays)
        logger.info(f"📌 Pinned message updated for {guild_name}")
    except Exception as e:
        logger.error(f"❌ Failed to update pinned message for {guild_name}: {e}")

# -------------------- Remove Birthday Roles --------------------
async def remove_birthday_roles(guild: discord.Guild):
    config = await get_guild_config(str(guild.id))
    role = None
    if config and config.get("birthday_role_id"):
        try:
            role_id_int = int(config["birthday_role_id"])
            role = guild.get_role(role_id_int)
            if not role and guild.id not in already_logged_missing_roles_remove:
                logger.warning(f"❗ Birthday role {role_id_int} not found in {guild.name}. Skipping removal.")
                already_logged_missing_roles_remove.add(guild.id)
        except (TypeError, ValueError):
            logger.warning(f"❗ Invalid birthday role ID in {guild.name}, skipping removal.")

    if role:
        for member in guild.members:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="Birthday day ended")
                except Exception as e:
                    logger.error(f"❌ Error removing birthday role from {member.display_name}: {e}")

# -------------------- Birthday Check Loop --------------------
async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 5):
    await ensure_wished_table()
    await clear_old_wishes()  # Clean old entries (7 days default)
    logger.info(f"🕒 Birthday check loop started (every {interval_minutes} minutes)")

    last_checked_date = None
    already_checked_guilds = set()
    last_heartbeat = None
    HEARTBEAT_INTERVAL = 30

    await asyncio.sleep(5)

    while True:
        now = dt.datetime.now(dt.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        current_hour = now.hour

        if last_checked_date != today_str:
            last_checked_date = today_str
            already_checked_guilds.clear()

        for guild in bot.guilds:
            config = await get_guild_config(str(guild.id))
            if not config or "check_hour" not in config:
                continue

            check_hour = int(config["check_hour"])
            if guild.id in already_checked_guilds:
                continue

            if current_hour >= check_hour:
                await remove_birthday_roles(guild)
                await check_and_send_birthdays(guild)
                already_checked_guilds.add(guild.id)

        if last_heartbeat is None or (now - last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL * 60:
            logger.info(f"💓 Birthday check loop alive at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            last_heartbeat = now

        await asyncio.sleep(interval_minutes * 60)

# -------------------- Run Once for Test --------------------
async def run_birthday_check_once(bot: discord.Client, guild: discord.Guild = None, test_date: dt.datetime = None, reset_wished: bool = False):
    await ensure_wished_table()

    date_str = (test_date or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%d")

    if reset_wished and guild:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "DELETE FROM wished_today WHERE guild_id = ? AND date = ?",
                (str(guild.id), date_str)
            )
            await db.commit()
        logger.info(f"🗑️ Cleared wished users for {guild.name} (test run)")

    if guild:
        await remove_birthday_roles(guild)
        await check_and_send_birthdays(guild, today_override=test_date, ignore_wished=False)
    else:
        for g in bot.guilds:
            await remove_birthday_roles(g)
            await check_and_send_birthdays(g, today_override=test_date, ignore_wished=False)
