import os
import discord
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

DB_FILE = "birthdays.db"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
