import aiosqlite
import datetime as dt
import random

DB_FILE = "birthdays.db"
TEST_GUILD_ID = "1415476237618647154"  # Replace with your testing server ID

FIRST_NAMES = [
    "Hiba", "Kethavin", "Arvaamaton", "Erla", "Can", "Liora", "Zane", "Talia",
    "Milo", "Aurora", "Finn", "Selene", "Ronan", "Isla", "Ezra", "Nova", "Leo", "Vera"
]
LAST_NAMES = [
    "Dice", "Hans", "Moon", "Starfall", "River", "Lightfoot", "Shadow", "Vale",
    "Storm", "Frost", "Ember", "Skye", "Dusk", "Flame", "Wren"
]

async def generate_realistic_name(index):
    # Pick random first and last name, add some flair for uniqueness
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    special = "" if index % 5 else "⭐"  # Add a star every 5th user
    return f"{first} {last}{special}"

async def populate_fake_birthdays():
    today = dt.datetime.now(dt.timezone.utc)
    today_str = f"{today.month:02d}-{today.day:02d}"

    async with aiosqlite.connect(DB_FILE) as db:
        for i in range(1, 91):
            user_id = str(100000000000000000 + i)  # fake user IDs
            name = await generate_realistic_name(i)

            # Make 3 random users have birthday today
            if i <= 3:
                birthday_str = today_str
            else:
                month = random.randint(1, 12)
                day = random.randint(1, 28 if month == 2 else 30 if month in [4, 6, 9, 11] else 31)
                birthday_str = f"{month:02d}-{day:02d}"

            await db.execute(
                "INSERT OR REPLACE INTO birthdays (guild_id, user_id, birthday) VALUES (?, ?, ?)",
                (TEST_GUILD_ID, user_id, birthday_str)
            )

        await db.commit()
    print("✅ Populated 90+ realistic fake birthdays, including a few for today!")

# Run the function
import asyncio
asyncio.run(populate_fake_birthdays())
