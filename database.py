import aiosqlite

DB_PATH = "birthdays.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id TEXT PRIMARY KEY,
                birthday TEXT
            )
        """)
        await db.commit()

async def set_birthday(user_id: str, birthday: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "REPLACE INTO birthdays (user_id, birthday) VALUES (?, ?)",
            (user_id, birthday)
        )
        await db.commit()

async def get_birthdays():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id, birthday FROM birthdays")
        return await cursor.fetchall()
