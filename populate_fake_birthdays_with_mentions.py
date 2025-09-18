# populate_fake_birthdays_enhanced.py
import aiosqlite
import random
import datetime as dt
import asyncio

DB_FILE = "birthdays.db"          # Your bot's DB file
GUILD_ID = "1415476237618647154"   # Replace with your server ID
NUM_USERS = 100                    # Total fake users to create
TODAY_BIRTHDAYS = 3               # How many users to have birthday today

# Example names for fake users
FIRST_NAMES = ["Alex", "Sam", "Jordan", "Taylor", "Chris", "Pat", "Jamie", "Morgan", "Casey", "Drew"]
LAST_NAMES = ["Smith", "Johnson", "Lee", "Brown", "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson"]

def random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

async def populate_fake_users():
    today = dt.datetime.now(dt.timezone.utc)
    today_str = f"{today.month:02d}-{today.day:02d}"

    async with aiosqlite.connect(DB_FILE) as db:
        # Ensure table exists
        await db.execute("""
        CREATE TABLE IF NOT EXISTS birthdays (
            guild_id TEXT,
            user_id TEXT,
            birthday TEXT,
            PRIMARY KEY (guild_id, user_id)
        )
        """)
        await db.commit()

        # Pre-generate user IDs and birthdays
        birthdays_assigned_today = 0

        for i in range(1, NUM_USERS + 1):
            user_id = str(100000000000000000 + i)  # Fake Discord ID

            # Decide if this user should have birthday today
            if birthdays_assigned_today < TODAY_BIRTHDAYS and random.random() < 0.1:
                birthday_str = today_str
                birthdays_assigned_today += 1
            else:
                month = random.randint(1, 12)
                if month in [4, 6, 9, 11]:
                    day = random.randint(1, 30)
                elif month == 2:
                    day = random.randint(1, 28)
                else:
                    day = random.randint(1, 31)
                birthday_str = f"{month:02d}-{day:02d}"

            # Insert into DB
            await db.execute(
                "INSERT OR REPLACE INTO birthdays (guild_id, user_id, birthday) VALUES (?, ?, ?)",
                (GUILD_ID, user_id, birthday_str)
            )

        await db.commit()
        print(f"✅ Populated {NUM_USERS} fake users in guild {GUILD_ID}, with {birthdays_assigned_today} birthdays today.")

if __name__ == "__main__":
    asyncio.run(populate_fake_users())
