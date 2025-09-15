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
logged_missing_channels = set()
logged_missing_roles = set()
logged_missing_roles_remove = set()

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

    # --- Channel ---
    channel_id = config.get("channel_id")
    channel = guild.get_channel(channel_id)
    if not channel and guild.id not in logged_missing_channels:
        visible_channels = [(c.name, c.id) for c in guild.channels][:10]
        if len(guild.channels) > 10:
            visible_channels.append(("...", "..."))
        logger.warning(f"Birthday channel {channel_id} not found in guild {guild.name} ({guild.id}). "
                       f"Visible channels (first 10): {visible_channels}")
        logged_missing_channels.add(guild.id)
        return
    elif channel:
        logger.info(f"Using birthday channel: {channel.name} ({channel.id}) in {guild.name}")

    # --- Role ---
    role_id = config.get("birthday_role_id")
    role = guild.get_role(role_id) if role_id else None
    if not role and role_id and guild.id not in logged_missing_roles:
        visible_roles = [(r.name, r.id) for r in guild.roles][:10]
        if len(guild.roles) > 10:
            visible_roles.append(("...", "..."))
        logger.warning(f"Birthday role {role_id} not found in guild {guild.name} ({guild.id}). "
                       f"Visible roles (first 10): {visible_roles}")
        logged_missing_roles.add(guild.id)
    elif role:
        logger.info(f"Using birthday role: {role.name} ({role.id}) in {guild.name}")

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

                # --- Add Birthday Role ---
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Birthday!")
                        logger.info(f"Added birthday role to {member.display_name} in {guild.name}")
                    except discord.Forbidden:
                        logger.warning(f"Cannot add birthday role to {member.display_name} in {guild.name}")
                        await channel.send(f"⚠️ Cannot add birthday role to {member.mention}. Check permissions.", delete_after=10)
                    except Exception as e:
                        logger.error(f"Error adding birthday role to {member.display_name} in {guild.name}: {e}")
                        await channel.send(f"🚨 Error adding birthday role to {member.mention}. Try again later.", delete_after=10)

            if not ignore_wished:
                await mark_as_wished(guild_id, user_id, date_str)

    # --- Update Pinned Message ---
    try:
        await update_pinned_birthday_message(guild, highlight_today=todays_birthdays or None)
    except Exception as e:
        logger.warning(f"Could not refresh pinned message for {guild.name}: {e}")


# -------------------- Remove Birthday Roles --------------------
async def remove_birthday_roles(guild: discord.Guild):
    config = await get_guild_config(str(guild.id))
    if not config or not config.get("birthday_role_id"):
        return

    role_id = config.get("birthday_role_id")
    role = guild.get_role(role_id)
    if not role and guild.id not in logged_missing_roles_remove:
        logger.warning(f"Birthday role {role_id} not found in guild {guild.name}. Skipping role removal.")
        logged_missing_roles_remove.add(guild.id)
        return

    for member in guild.members:
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Birthday day ended")
                logger.debug(f"Removed birthday role from {member.display_name} in {guild.name}")
            except discord.Forbidden:
                logger.warning(f"Cannot remove birthday role from {member.display_name} in {guild.name}.")
            except Exception as e:
                logger.error(f"Error removing birthday role from {member.display_name} in {guild.name}: {e}")


# -------------------- Birthday Check Loop --------------------
async def birthday_check_loop(bot: discord.Client, interval_minutes: int = 5):
    await ensure_wished_table()
    last_checked_date = None
    already_checked_guilds = set()

    # --- Initial Catch-Up ---
    logger.info("🟢 Running initial birthday check (catch-up) for all guilds")
    now = dt.datetime.now(dt.timezone.utc)
    for guild in bot.guilds:
        config = await get_guild_config(str(guild.id))
        if config and "check_hour" in config:
            check_hour = int(config["check_hour"])
            if now.hour >= check_hour:
                await remove_birthday_roles(guild)
                await check_and_send_birthdays(guild, ignore_wished=True)
                already_checked_guilds.add(guild.id)

    # --- Main Loop ---
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        current_hour = now.hour

        # --- Clear old wishes once per day ---
        if last_checked_date != today_str:
            await clear_old_wishes(today_str)
            last_checked_date = today_str
            already_checked_guilds.clear()  # Reset daily check tracking

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

        await asyncio.sleep(interval_minutes * 60)


# -------------------- Run Once for Test --------------------
async def run_birthday_check_once(bot: discord.Client, guild: discord.Guild = None, test_date: dt.datetime = None):
    await ensure_wished_table()
    if guild:
        await remove_birthday_roles(guild)
        await check_and_send_birthdays(guild, today_override=test_date, ignore_wished=True)
    else:
        for g in bot.guilds:
            await remove_birthday_roles(g)
            await check_and_send_birthdays(g, today_override=test_date, ignore_wished=True)
