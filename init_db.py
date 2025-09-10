import aiosqlite
import asyncio

DB_FILE = "birthdays.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # Create birthdays table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id TEXT PRIMARY KEY,
                birthday TEXT NOT NULL
            )
            """
        )

        # Create config table to store pinned message ID or other settings
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        await db.commit()
    print(f"✅ Database '{DB_FILE}' initialized successfully!")

# Run the initializer
asyncio.run(init_db())
