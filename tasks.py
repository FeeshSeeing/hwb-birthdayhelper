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

async def clear_old_wishes(date_str: str):
    logger.info(f"🧹 Clearing old wished_today entries (keeping only {date_str})")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM wished_today WHERE date != ?", (date_str,))
        await db.commit()
    logger.debug("✅ Old wishes cleared.")

# -------------------- Birthday Check --------------------
logged_missing_channels = set()
logged_missing_roles = set()
already_logged_missing_roles_remove = set()

async def check_and_send_birthdays(
    guild: discord.Guild,
    today_override: dt.datetime = None,
    ignore_wished: bool = False
):
    guild_id = str(guild.id)
    logger.info(f"🔍 Checking birthdays for guild {guild.name} ({guild.id})...")
    config = await get_guild_config(guild_id)
    if not config:
        logger.warning(f"⚠️ No config found for guild {guild.name} ({guild.id}) — skipping.")
        return

    # --- Channel ---
    channel_id = config.get("channel_id")
    logger.debug(f"Config for {guild.name}: channel_id={channel_id}, birthday_role_id={config.get('birthday_role_id')}")
    channel = guild.get_channel(channel_id)
    if not channel:
        if guild.id not in logged_missing_channels:
            visible_channels = [(c.name, c.id) for c in guild.channels][:10]
            if len(guild.channels) > 10:
                visible_channels.append(("...", "..."))
            logger.warning(
                f"❌ Birthday channel {channel_id} not found in guild {guild.name} ({guild.id}). "
                f"Visible channels (first 10): {visible_channels}"
            )
            logged_missing_channels.add(guild.id)
        return
    logger.info(f"✅ Using birthday channel: {channel.name} ({channel.id}) in {guild.name}")

    # --- Role ---
    role_id = config.get("birthday_role_id")
    role = guild.get_role(role_id) if role_id else None
    if not role and role_id:
        if guild.id not in logged_missing_roles:
            visible_roles = [(r.name, r.id) for r in guild.roles][:10]
            if len(guild.roles) > 10:
                visible_roles.append(("...", "..."))
            logger.warning(
                f"❌ Birthday role {role_id} not found in guild {guild.name}. "
                f"Visible roles (first 10): {visible_roles}"
            )
            logged_missing_roles.add(guild.id)
    elif role:
        logger.debug(f"✅ Using birthday role: {role.name} ({role.id})")

    now = today_override or dt.datetime.now(dt.timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    logger.debug(f"Current UTC time: {now.isoformat()} (date_str={date_str})")

    birthdays = await get_birthdays(guild_id)
    logger.info(f"📋 Found {len(birthdays)} birthday entries in DB for {guild.name}")
    todays_birthdays = []

    for user_id, birthday in birthdays:
        logger.debug(f"👤 Checking user {user_id} with birthday {birthday}")
        if is_birthday_on_date(birthday, now):
            logger.info(f"🎂 Today matches {user_id}'s birthday ({birthday})!")
            if not ignore_wished:
                already_wished = await has_been_wished(guild_id, user_id, date_str)
                if already_wished:
                    logger.debug(f"⏩ Skipping {user_id} (already wished today).")
                    continue

            todays_birthdays.append(user_id)
            member = guild.get_member(int(user_id))
            if member:
                logger.debug(f"Preparing to send birthday message to {member.display_name} ({member.id})")
                try:
                    await channel.send(
                        f"🎉 Happy Birthday, {member.mention}! 🎈\n"
                        f"From all of us at **{guild.name}**, sending you lots of love today 💖🎂"
                    )
                    logger.info(f"✅ Sent birthday message for {member.display_name} in {guild.name}")
                except Exception as e:
                    logger.error(f"❌ Failed to send birthday message for {member.display_name} in {guild.name}: {e}")

                if role and role not in member.roles:
                    try:
                        logger.debug(f"Adding birthday role {role.name} to {member.display_name}")
                        await member.add_roles(role, reason="Birthday!")
                        logger.info(f"✅ Added birthday role to {member.display_name} in {guild.name}")
                    except discord.Forbidden:
                        logger.warning(f"⚠️ Cannot add birthday role to {member.display_name} (permissions issue).")
                        await channel.send(
                            f"⚠️ Cannot add birthday role to {member.mention}. Check bot permissions.",
                            delete_after=10
                        )
                    except Exception as e:
                        logger.error(f"❌ Error adding birthday role to {member.display_name}: {e}")
                        await channel.send(
                            f"🚨 Error adding birthday role to {member.mention}. Try again later.",
                            delete_after=10
                        )

            else:
                logger.warning(f"⚠️ User {user_id} not found in {guild.name} (probably left the server).")

            if not ignore_wished:
                await mark_as_wished(guild_id, user_id, date_str)

    try:
        logger.debug(f"Updating pinned birthday message with highlights: {todays_birthdays}")
        await update_pinned_birthday_message(guild, highlight_today=todays_birthdays)
        logger.info(f"📌 Pinned message updated for {guild.name}")
    except Exception as e:
        logger.error(f"❌ Failed to update pinned message for {guild.name}: {e}")

# -------------------- Remove Birthday Roles --------------------
async def remove_birthday_roles(guild: discord.Guild):
    logger.debug(f"Checking for expired birthday roles in {guild.name}")
    config = await get_guild_config(str(guild.id))
    if not config or not config.get("birthday_role_id"):
        logger.debug(f"No birthday_role_id set for {guild.name}, skipping removal.")
        return

    role_id = config.get("birthday_role_id")
    role = guild.get_role(role_id)
    if not role:
        if guild.id not in already_logged_missing_roles_remove:
            logger.warning(f"⚠️ Birthday role {role_id} not found in {guild.name}. Skipping removal.")
            already_logged_missing_roles_remove.add(guild.id)
        return

    for member in guild.members:
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Birthday day ended")
                logger.debug(f"Removed birthday role from {member.display_name}")
            except discord.Forbidden:
                logger.warning(f"⚠️ Cannot remove birthday role from {member.display_name}.")
            except Exception as e:
                logger.error(f"❌ Error removing birthday role from {member.display_name}: {e}")

# -------------------- Birthday Check Loop --------------------
async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 5):
    await ensure_wished_table()
    last_checked_date = None
    already_checked_guilds = set()
    last_heartbeat = None
    HEARTBEAT_INTERVAL = 30  # minutes

    logger.info("🟢 Initial birthday check (catch-up) starting...")
    await asyncio.sleep(5)
    now = dt.datetime.now(dt.timezone.utc)
    for guild in bot.guilds:
        config = await get_guild_config(str(guild.id))
        if config and "check_hour" in config:
            check_hour = int(config["check_hour"])
            logger.debug(f"{guild.name}: check_hour={check_hour}, now.hour={now.hour}")
            if now.hour >= check_hour:
                logger.debug(f"Performing catch-up check for {guild.name}")
                await remove_birthday_roles(guild)
                await check_and_send_birthdays(guild, ignore_wished=True)
                already_checked_guilds.add(guild.id)

    logger.info(f"🕒 Birthday check loop started (every {interval_minutes} minutes)")

    while True:
        now = dt.datetime.now(dt.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        current_hour = now.hour

        if last_checked_date != today_str:
            logger.info(f"🔄 New day detected: {today_str} — clearing old wishes")
            await clear_old_wishes(today_str)
            last_checked_date = today_str
            already_checked_guilds.clear()

        for guild in bot.guilds:
            config = await get_guild_config(str(guild.id))
            if not config or "check_hour" not in config:
                logger.debug(f"{guild.name}: No check_hour set, skipping.")
                continue

            check_hour = int(config["check_hour"])
            logger.debug(f"{guild.name}: current_hour={current_hour}, check_hour={check_hour}")
            if guild.id in already_checked_guilds:
                logger.debug(f"{guild.name}: already checked today, skipping.")
                continue
            if current_hour >= check_hour:
                logger.debug(f"Triggering birthday check for {guild.name}")
                await remove_birthday_roles(guild)
                await check_and_send_birthdays(guild)
                already_checked_guilds.add(guild.id)
                logger.info(f"✅ Birthday check cycle finished for {guild.name} (hour={current_hour})")
            else:
                logger.debug(f"{guild.name}: Not time yet (waiting for check_hour)")

        if last_heartbeat is None or (now - last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL * 60:
            logger.info(f"💓 Birthday check loop alive at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            last_heartbeat = now

        await asyncio.sleep(interval_minutes * 60)