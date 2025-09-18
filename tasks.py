import asyncio
import discord
import datetime as dt
from logger import logger
from utils import update_pinned_birthday_message, is_birthday_on_date

# -------------------- Globals --------------------
already_logged_missing_roles_remove = set()
already_logged_missing_roles_add = set()

# -------------------- Wished Table --------------------
async def ensure_wished_table(db):
    """Ensure wished_today table exists."""
    logger.debug("Ensuring wished_today table exists in DB...")
    await db.db.execute("""
        CREATE TABLE IF NOT EXISTS wished_today (
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id, date)
        )
    """)
    await db.db.commit()
    logger.debug("✅ wished_today table check complete.")

async def has_been_wished(db, guild_id: str, user_id: str, date_str: str) -> bool:
    async with db.db.execute(
        "SELECT 1 FROM wished_today WHERE guild_id = ? AND user_id = ? AND date = ?",
        (guild_id, user_id, date_str)
    ) as cursor:
        result = await cursor.fetchone()
        logger.debug(f"has_been_wished? guild={guild_id}, user={user_id}, date={date_str} -> {bool(result)}")
        return result is not None

async def mark_as_wished(db, guild_id: str, user_id: str, date_str: str):
    logger.debug(f"Marking user {user_id} as wished in guild {guild_id} for {date_str}")
    await db.db.execute(
        "INSERT OR IGNORE INTO wished_today (guild_id, user_id, date) VALUES (?, ?, ?)",
        (guild_id, user_id, date_str)
    )
    await db.db.commit()

async def clear_old_wishes(db, retain_days: int = 7):
    """Delete wished_today entries older than retain_days."""
    today = dt.datetime.now(dt.timezone.utc)
    cutoff_date = (today - dt.timedelta(days=retain_days)).strftime("%Y-%m-%d")
    logger.info(f"🧹 Clearing wished_today entries older than {cutoff_date}")
    await db.db.execute("DELETE FROM wished_today WHERE date < ?", (cutoff_date,))
    await db.db.commit()
    logger.debug("✅ Old wishes cleared.")

# -------------------- Birthday Check --------------------
async def check_and_send_birthdays(bot, db, guild: discord.Guild, today_override: dt.datetime = None, ignore_wished: bool = False):
    guild_name = guild.name
    guild_id = str(guild.id)
    logger.info(f"🔍 Checking birthdays for guild {guild_name}...")

    config = await db.get_guild_config(guild_id)
    if not config:
        logger.warning(f"❗ No config found for guild {guild_name} — skipping.")
        return

    # Resolve channel
    channel_id = config.get("channel_id")
    if not channel_id:
        logger.warning(f"❗ No channel ID set for {guild_name}.")
        return

    channel = guild.get_channel(int(channel_id)) or await guild.fetch_channel(int(channel_id))
    perms = channel.permissions_for(guild.me)
    if not perms.send_messages:
        logger.error(f"Cannot send messages in channel {channel.name} ({channel.id})")
        return

    # Resolve birthday role
    role_id = config.get("birthday_role_id")
    role = None
    if role_id:
        try:
            role_id_str = str(role_id)
            role = guild.get_role(int(role_id_str))
            if not role and str(guild.id) not in already_logged_missing_roles_add:
                try:
                    role = await guild.fetch_role(int(role_id_str))
                    logger.info(f"✅ Fetched birthday role {role.name} via API for {guild_name}")
                except Exception as e:
                    logger.warning(f"❗ Cannot find/access birthday role {role_id_str} in {guild_name}: {e}")
                    already_logged_missing_roles_add.add(str(guild.id))
        except (TypeError, ValueError):
            logger.warning(f"❗ Invalid birthday role ID in {guild_name}, skipping role assignment.")

    now = today_override or dt.datetime.now(dt.timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    birthdays = await db.get_birthdays(guild_id)
    logger.info(f"📋 Found {len(birthdays)} birthday entries in DB for {guild_name}")
    todays_birthdays = []

    sent_this_loop = set()
    for user_id, birthday in birthdays:
        user_id = str(user_id)
        if user_id in sent_this_loop:
            continue

        if is_birthday_on_date(birthday, now):
            if not ignore_wished and await has_been_wished(db, guild_id, user_id, date_str):
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

                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Birthday!")
                        logger.info(f"✅ Added birthday role to {member.display_name} in {guild_name}")
                    except Exception as e:
                        logger.warning(f"❗ Could not add birthday role to {member.display_name}: {e}")

            if not ignore_wished:
                await mark_as_wished(db, guild_id, user_id, date_str)

    # Update pinned message
    try:
        await update_pinned_birthday_message(guild, db=db, highlight_today=todays_birthdays)
        logger.info(f"📌 Pinned message updated for {guild_name}")
    except Exception as e:
        logger.error(f"❌ Failed to update pinned message for {guild_name}: {e}")

# -------------------- Remove Birthday Roles --------------------
async def remove_birthday_roles(db, guild: discord.Guild):
    config = await db.get_guild_config(str(guild.id))
    role = None
    if config and config.get("birthday_role_id"):
        try:
            role_id_str = str(config["birthday_role_id"])
            role = guild.get_role(int(role_id_str))
            if not role and str(guild.id) not in already_logged_missing_roles_remove:
                logger.warning(f"❗ Birthday role {role_id_str} not found in {guild.name}. Skipping removal.")
                already_logged_missing_roles_remove.add(str(guild.id))
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
    db = bot.db
    await ensure_wished_table(db)
    await clear_old_wishes(db)
    logger.info(f"🕒 Birthday check loop started (every {interval_minutes} minutes)")

    last_reset_date = None
    already_checked_guilds = set()
    last_heartbeat = None
    HEARTBEAT_INTERVAL = 30

    await asyncio.sleep(5)

    while True:
        now = dt.datetime.now(dt.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        current_hour = now.hour

        # Role reset + pinned refresh at UTC midnight
        if last_reset_date != today_str and now.hour == 0:
            logger.info("🌙 Midnight UTC reached. Removing birthday roles and refreshing pinned messages.")
            for guild in bot.guilds:
                await remove_birthday_roles(db, guild)
                try:
                    await update_pinned_birthday_message(guild, db=db)
                    logger.info(f"📌 Pinned message refreshed in {guild.name}")
                except Exception as e:
                    logger.error(f"❌ Failed to refresh pinned message for {guild.name}: {e}")
            last_reset_date = today_str
            already_checked_guilds.clear()

        # Birthday wishes (respect check_hour)
        for guild in bot.guilds:
            config = await db.get_guild_config(str(guild.id))
            if not config or "check_hour" not in config:
                continue

            check_hour = int(config["check_hour"])
            if guild.id in already_checked_guilds:
                continue

            if current_hour >= check_hour:
                await check_and_send_birthdays(bot, db, guild)
                already_checked_guilds.add(guild.id)

        # Heartbeat logging
        if last_heartbeat is None or (now - last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL * 60:
            logger.info(f"💓 Birthday check loop alive at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            last_heartbeat = now

        await asyncio.sleep(interval_minutes * 60)

# -------------------- Run Once for Test --------------------
async def run_birthday_check_once(bot, guild: discord.Guild = None, test_date: dt.datetime = None, reset_wished: bool = False):
    db = bot.db
    await ensure_wished_table(db)
    date_str = (test_date or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%d")

    if reset_wished and guild:
        await db.db.execute(
            "DELETE FROM wished_today WHERE guild_id = ? AND date = ?",
            (str(guild.id), date_str)
        )
        await db.db.commit()
        logger.info(f"🗑️ Cleared wished users for {guild.name} (test run)")

    targets = [guild] if guild else bot.guilds
    for g in targets:
        await remove_birthday_roles(db, g)
        await check_and_send_birthdays(bot, db, g, today_override=test_date)
