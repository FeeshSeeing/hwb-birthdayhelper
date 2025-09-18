# database.py
import aiosqlite
from config import DB_FILE
from logger import logger

class Database:
    """Manages all database operations with a single, persistent connection."""

    def __init__(self, db_file: str):
        """Initializes the Database manager."""
        self.db_file = db_file
        self.db: aiosqlite.Connection | None = None

    async def connect(self):
        """Establishes the database connection and sets up the row factory."""
        if self.db is not None:
            logger.warning("⚠️ Database already connected.")
            return  # <-- only return if already connected

        self.db = await aiosqlite.connect(self.db_file)
        self.db.row_factory = aiosqlite.Row
        logger.info("✅ Database connection established.")

    async def close(self):
        """Closes the database connection if it exists."""
        if self.db:
            await self.db.close()
            logger.info("❌ Database connection closed.")

    async def init_db(self):
        """Creates the necessary tables if they do not already exist."""
        # Note: All ID columns are now INTEGER for better performance and storage.
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                birthday TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                birthday_role_id INTEGER,
                mod_role_id INTEGER,
                check_hour INTEGER DEFAULT 9
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await self.db.commit()
        logger.info("✅ Database tables initialized.")

    # -------------------- Birthday Operations --------------------
    async def set_birthday(self, guild_id: int, user_id: int, birthday: str):
        """Sets or updates a user's birthday in a specific guild."""
        await self.db.execute(
            "INSERT OR REPLACE INTO birthdays (guild_id, user_id, birthday) VALUES (?, ?, ?)",
            (guild_id, user_id, birthday),
        )
        await self.db.commit()

    async def delete_birthday(self, guild_id: int, user_id: int):
        """Deletes a user's birthday from a specific guild."""
        await self.db.execute(
            "DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.db.commit()

    async def get_birthdays(self, guild_id: int) -> list[tuple[int, str]]:
        """Fetches all birthdays for a given guild."""
        try:
            async with self.db.execute(
                "SELECT user_id, birthday FROM birthdays WHERE guild_id = ?", (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                # Convert list of Row objects to a list of tuples
                return [(row["user_id"], row["birthday"]) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching birthdays for guild {guild_id}: {e}", exc_info=True)
            return []

    # -------------------- Guild Config Operations --------------------
    async def set_guild_config(self, guild_id: int, channel_id: int, birthday_role_id: int | None, mod_role_id: int | None, check_hour: int):
        """Sets or updates the configuration for a guild."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO guild_config (guild_id, channel_id, birthday_role_id, mod_role_id, check_hour)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, birthday_role_id, mod_role_id, check_hour),
        )
        await self.db.commit()
        logger.info(f"⚙️ Guild config updated for {guild_id}")

    async def get_guild_config(self, guild_id: int) -> dict | None:
        """Fetches the configuration for a specific guild."""
        async with self.db.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            # Convert the Row object to a dictionary if a record was found
            return dict(row) if row else None

    # -------------------- Generic Config Operations --------------------
    async def set_config_value(self, key: str, value: str):
        """Sets a generic key-value pair in the config table."""
        await self.db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value)
        )
        await self.db.commit()
        logger.debug(f"Config value set: {key} = {value}")

    async def get_config_value(self, key: str) -> str | None:
        """Gets a value from the generic config table by its key."""
        async with self.db.execute("SELECT value FROM config WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row["value"] if row else None