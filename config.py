import os
from dotenv import load_dotenv

load_dotenv()

DB_FILE = "birthdays.db"
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
BIRTHDAY_INTERVAL_MINUTES = 5
GUILD_IDS = []  # Add test guild IDs here if needed