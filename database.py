import aiosqlite
from logger import logger

DB_FILE = "birthdays.db"

async def init_db():
    logger.info("Initializing database...")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                mod_role_id TEXT,
                birthday_role_id TEXT,
                check_hour INTEGER DEFAULT 9
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                birthday TEXT NOT NULL,
                PRIMARY KEY(guild_id, user_id)
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

async def get_guild_config(guild_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT channel_id, mod_role_id, birthday_role_id, check_hour FROM guild_config WHERE guild_id=?",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "channel_id": int(row[0]),
                    "mod_role_id": int(row[1]) if row[1] else None,
                    "birthday_role_id": int(row[2]) if row[2] else None,
                    "check_hour": int(row[3])
                }
    return None

async def get_birthdays(guild_id: str):
    birthdays = []
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT user_id, birthday FROM birthdays WHERE guild_id=?", (guild_id,)
        ) as cursor:
            async for row in cursor:
                birthdays.append((row[0], row[1]))
    return birthdays

async def set_birthday(guild_id: str, user_id: str, birthday_str: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO birthdays (guild_id, user_id, birthday) VALUES (?, ?, ?)",
            (guild_id, user_id, birthday_str)
        )
        await db.commit()
        logger.info(f"🎂 Birthday saved for user {user_id} in guild {guild_id}: {birthday_str}")

async def delete_birthday(guild_id: str, user_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )
        await db.commit()
        logger.info(f"🗑️ Birthday deleted for user {user_id} in guild {guild_id}")
