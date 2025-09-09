import os
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv
import datetime
import aiosqlite

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
CHECK_HOUR = int(os.getenv("CHECK_HOUR", 9))  # default 9 AM

# -----------------------------
# Set Discord intents
# -----------------------------
intents = discord.Intents.default()
intents.members = True  # Needed to access guild members
intents.message_content = True  # Needed to read messages if you want

bot = commands.Bot(command_prefix="!", intents=intents)

# Track users already wished today
already_wished_today = set()

# -----------------------------
# Database helper
# -----------------------------
async def get_birthdays():
    """Fetch all birthdays from the database"""
    birthdays = []
    async with aiosqlite.connect("birthdays.db") as db:
        async with db.execute("SELECT user_id, birthday FROM birthdays") as cursor:
            async for row in cursor:
                birthdays.append((row[0], row[1]))
    return birthdays

async def set_birthday(user_id: str, birthday_str: str):
    """Insert or update birthday in the database"""
    async with aiosqlite.connect("birthdays.db") as db:
        await db.execute(
            "INSERT INTO birthdays (user_id, birthday) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET birthday = excluded.birthday",
            (user_id, birthday_str)
        )
        await db.commit()

# -----------------------------
# Birthday check task
# -----------------------------
@tasks.loop(minutes=60)
async def birthday_check():
    now = datetime.datetime.now()
    today_str = now.strftime("%m-%d")

    # Reset daily record at midnight
    if now.hour == 0 and now.minute < 60:
        already_wished_today.clear()

    # Only check at or after CHECK_HOUR
    if now.hour != CHECK_HOUR:
        return

    birthdays = await get_birthdays()
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    channel = guild.get_channel(CHANNEL_ID)
    if not channel:
        return

    for user_id, birthday in birthdays:
        if birthday == today_str and user_id not in already_wished_today:
            member = guild.get_member(int(user_id))
            if member:
                await channel.send(f"It's a special day for {member.mention} 🥳 May your year be full of joy, laughter, and warm hugs 🤗 ~ from Hugs without Borders")
                already_wished_today.add(user_id)

# -----------------------------
# Commands
# -----------------------------
@bot.command()
async def setbirthday(ctx, month: int, day: int):
    """User sets their own birthday"""
    user_id = str(ctx.author.id)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        await ctx.send("Invalid date! Use numbers like `!setbirthday 9 9` for September 9.")
        return

    birthday_str = f"{month:02d}-{day:02d}"
    await set_birthday(user_id, birthday_str)
    await ctx.send(f"Your birthday is saved on our calendar, {birthday_str} 📅 Can't wait to share the joy with you!")

@bot.command()
@commands.has_permissions(administrator=True)
async def setuserbirthday(ctx, member: discord.Member, month: int, day: int):
    """Admin sets birthday for any user"""
    user_id = str(member.id)
    birthday_str = f"{month:02d}-{day:02d}"
    await set_birthday(user_id, birthday_str)
    await ctx.send(f"{member.display_name}'s birthday has been set to {birthday_str} 🎉")

# -----------------------------
# Bot events
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    birthday_check.start()

# -----------------------------
# Run bot
# -----------------------------
bot.run(TOKEN)
