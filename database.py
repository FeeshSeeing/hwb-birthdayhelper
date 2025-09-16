# database.py
import aiosqlite
from config import DB_FILE
from logger import logger

# -------------------- Initialize Database --------------------
async def init_db():
    """Create necessary tables if they do not exist."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                birthday TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                birthday_role_id TEXT,
                mod_role_id TEXT,
                check_hour INTEGER DEFAULT 9
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()
    logger.info("✅ Database initialized.")


# -------------------- Birthday Operations --------------------
async def set_birthday(guild_id: str, user_id: str, birthday: str, username: str | None = None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO birthdays (guild_id, user_id, birthday) VALUES (?, ?, ?)",
            (guild_id, user_id, birthday)
        )
        await db.commit()
    user_display = username if username else user_id
    logger.info(f"🎂 Birthday saved for user {user_display} in guild {guild_id}: {birthday}")


async def delete_birthday(guild_id: str, user_id: str, username: str | None = None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        await db.commit()
    user_display = username if username else user_id
    logger.info(f"🗑️ Birthday deleted for user {user_display} in guild {guild_id}")


async def get_birthdays(guild_id: str) -> list[tuple[str, str]]:
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute(
                "SELECT user_id, birthday FROM birthdays WHERE guild_id = ?", (guild_id,)
            )
            rows = await cursor.fetchall()
            await cursor.close()
            logger.debug(f"Fetched {len(rows)} birthdays for guild {guild_id}")
            return rows
    except Exception as e:
        logger.error(f"Error fetching birthdays for guild {guild_id}: {e}", exc_info=True)
        return []


# -------------------- Guild Config Operations --------------------
async def set_guild_config(
    guild_id: str,
    channel_id: str,
    birthday_role_id: str | None,
    mod_role_id: str | None,
    check_hour: int
):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO guild_config (guild_id, channel_id, birthday_role_id, mod_role_id, check_hour)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, birthday_role_id, mod_role_id, check_hour)
        )
        await db.commit()
    logger.info(f"⚙️ Guild config updated for {guild_id}")


async def get_guild_config(guild_id: str) -> dict | None:
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT channel_id, birthday_role_id, mod_role_id, check_hour FROM guild_config WHERE guild_id = ?",
            (guild_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return {
                "channel_id": row[0],
                "birthday_role_id": row[1],
                "mod_role_id": row[2],
                "check_hour": row[3],
            }
        return None


# -------------------- Generic Config Operations --------------------
async def set_config_value(key: str, value: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value)
        )
        await db.commit()
    logger.debug(f"Config value set: {key} = {value}")


async def get_config_value(key: str) -> str | None:
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT value FROM config WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None
