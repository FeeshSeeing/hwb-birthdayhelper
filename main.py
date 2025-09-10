import os
import discord
from discord.ext import tasks, commands
from discord import app_commands
from dotenv import load_dotenv
import datetime
import aiosqlite
import calendar
import threading
from flask import Flask

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
CHECK_HOUR = int(os.getenv("CHECK_HOUR", 9))  # default 9 AM
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID", 0))
BIRTHDAY_ROLE_ID = int(os.getenv("BIRTHDAY_ROLE_ID"))
GUILD = discord.Object(id=GUILD_ID)


# ---- Flask server ----
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running on Render!"

def run_web():
    port = int(os.environ.get("PORT", 5000))  # Render sets $PORT
    app.run(host="0.0.0.0", port=port)

# Start Flask webserver in background thread
threading.Thread(target=run_web).start()

# -----------------------------
# Discord intents
# -----------------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Track users already wished today
already_wished_today = set()

# Database file
DB_FILE = "birthdays.db"

# -----------------------------
# Database Initialization
# -----------------------------
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id TEXT PRIMARY KEY,
                birthday TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()

# -----------------------------
# Database helpers
# -----------------------------
async def get_birthdays():
    birthdays = []
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id, birthday FROM birthdays") as cursor:
            async for row in cursor:
                birthdays.append((row[0], row[1]))
    return birthdays

async def set_birthday(user_id: str, birthday_str: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO birthdays (user_id, birthday) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET birthday = excluded.birthday",
            (user_id, birthday_str)
        )
        await db.commit()

async def delete_birthday(user_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM birthdays WHERE user_id = ?", (user_id,))
        await db.commit()

# -----------------------------
# Utility: parse day/month input
# -----------------------------
def parse_day_month_input(day_input: int, month_input: int):
    try:
        day = int(day_input)
        month = int(month_input)
        if 1 <= day <= 31 and 1 <= month <= 12:
            return day, month
        return None
    except ValueError:
        return None

# -----------------------------
# Utility: format birthday for display
# -----------------------------
def format_birthday_display(birthday_str: str) -> str:
    try:
        month_str, day_str = birthday_str.split("-")
        month = int(month_str)
        day = int(day_str)
        month_name = calendar.month_name[month]

        if 4 <= day <= 20 or 24 <= day <= 30:
            suffix = "th"
        else:
            suffix = ["st", "nd", "rd"][day % 10 - 1]

        return f"{day}{suffix} {month_name}"
    except:
        return birthday_str

# -----------------------------
# Pinned message helpers
# -----------------------------
async def update_pinned_birthday_message(guild: discord.Guild):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id, birthday FROM birthdays") as cursor:
            rows = await cursor.fetchall()

        # Build content
        if not rows:
            content = "📂 Oops! There are no birthdays in the database yet."
        else:
            content = "**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**\n"
            for user_id_str, birthday in rows:
                try:
                    user_id = int(user_id_str.replace("<@", "").replace(">", "").replace("!", ""))
                    member = guild.get_member(user_id)
                    name = member.display_name if member else str(user_id)
                    content += f"✦ {name}: {format_birthday_display(birthday)}\n"
                except:
                    content += f"❗ {user_id_str}: {birthday}\n"

        channel = guild.get_channel(CHANNEL_ID)
        if not channel:
            return

        # Fetch pinned message ID from DB
        async with db.execute("SELECT value FROM config WHERE key='pinned_birthday_msg'") as cursor:
            result = await cursor.fetchone()

        pinned_msg = None
        # Try fetching the pinned message by ID
        if result:
            try:
                pinned_msg = await channel.fetch_message(int(result[0]))
            except discord.NotFound:
                pinned_msg = None

        # If no pinned message found, look for any pinned messages by bot
        if not pinned_msg:
            pins = await channel.pins()
            bot_pins = [m for m in pins if m.author.id == guild.me.id]
            pinned_msg = bot_pins[0] if bot_pins else None

        # Edit existing pinned message or create a new one
        if pinned_msg:
            await pinned_msg.edit(content=content)
        else:
            pinned_msg = await channel.send(content)
            if channel.permissions_for(guild.me).manage_messages:
                await pinned_msg.pin()

        # Save pinned message ID
        await db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("pinned_birthday_msg", str(pinned_msg.id))
        )
        await db.commit()

# -----------------------------
# Birthday check loop
# -----------------------------
@tasks.loop(minutes=60)
## async def birthday_check(): ## use this one
async def birthday_check(force=False): ## test only
    now = datetime.datetime.now()
    today_str = now.strftime("%m-%d")

    ## test only
    if now.hour == 0 and now.minute < 60:
        already_wished_today.clear()
    if not force and now.hour != CHECK_HOUR:
        return
        
    ## use this one
    # if now.hour == 0 and now.minute < 60:
    #     already_wished_today.clear()

    # if now.hour != CHECK_HOUR:
    #     return

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
                await channel.send(f"Happy Birthday, {member.mention}!🎈 \nFrom all of us at Hugs without Borders, sending you lots of love today 💖🎂")
                
            if BIRTHDAY_ROLE_ID:
                    role = guild.get_role(BIRTHDAY_ROLE_ID)
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="Birthday!")
                        except discord.Forbidden:
                            await channel.send(f"⚠️ Cannot add birthday role to {member.mention}, missing permissions.")
            already_wished_today.add(user_id)

# -----------------------------
# Helper: is admin or mod
# -----------------------------
def is_admin_or_mod(member: discord.Member):
    # Full admins always allowed
    if member.guild_permissions.administrator:
        return True
    # Check for moderator role
    if MOD_ROLE_ID and any(role.id == MOD_ROLE_ID for role in member.roles):
        return True
    return False


# -----------------------------
# Bot events
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await init_db()
    birthday_check.start()
    try:
        synced = await bot.tree.sync(guild=GUILD)
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(e)

# -----------------------------
# Slash Commands (safe defer + followup + human-readable)
# -----------------------------

# /setbirthday
@bot.tree.command(name="setbirthday", description="Set your birthday (day then month)", guild=GUILD)
@app_commands.describe(day="Day of birthday", month="Month of birthday")
async def setbirthday(interaction: discord.Interaction, day: int, month: int):
    await interaction.response.defer(ephemeral=True)

    result = parse_day_month_input(day, month)
    if not result:
        await interaction.followup.send("❗Invalid day/month! Example: 25 12", ephemeral=True)
        return

    day, month = result
    birthday_str = f"{month:02d}-{day:02d}"
    await set_birthday(str(interaction.user.id), birthday_str)
    await update_pinned_birthday_message(interaction.guild)

    human_readable = format_birthday_display(birthday_str)
    await interaction.followup.send(f"All done 💌 Your special day is marked as {human_readable}. Hugs are on the way!", ephemeral=True)

# /deletebirthday
@bot.tree.command(name="deletebirthday", description="Delete your birthday", guild=GUILD)
async def deletebirthday(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await delete_birthday(str(interaction.user.id))
    await update_pinned_birthday_message(interaction.guild)
    await interaction.followup.send("All done🎈 Your birthday has been deleted. Don't worry, the hugs stay!", ephemeral=True)

# /listbirthdays
@bot.tree.command(name="listbirthdays", description="List all birthdays", guild=GUILD)
async def listbirthdays(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await update_pinned_birthday_message(interaction.guild)
    await interaction.followup.send("📌 Birthday list updated and pinned for everyone!", ephemeral=True)

# /setuserbirthday (admin or mod)
@bot.tree.command(name="setuserbirthday", description="Admin or Mod: set birthday for a user", guild=GUILD)
@app_commands.describe(user="User", day="Day", month="Month")
async def setuserbirthday(interaction: discord.Interaction, user: discord.Member, day: int, month: int):
    if not is_admin_or_mod(interaction.user):
        await interaction.response.send_message("❗Uh-oh! That action isn't allowed.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    result = parse_day_month_input(day, month)
    if not result:
        await interaction.followup.send("❗Invalid day/month!", ephemeral=True)
        return

    day, month = result
    birthday_str = f"{month:02d}-{day:02d}"
    await set_birthday(str(user.id), birthday_str)
    await update_pinned_birthday_message(interaction.guild)

    human_readable = format_birthday_display(birthday_str)
    await interaction.followup.send(f"💌 Got it! {user.display_name}'s birthday has been marked as {human_readable}.", ephemeral=True)

# /deleteuserbirthday (admin or mod)
@bot.tree.command(name="deleteuserbirthday", description="Admin or Mod: delete birthday for a user", guild=GUILD)
@app_commands.describe(user="User")
async def deleteuserbirthday(interaction: discord.Interaction, user: discord.Member):
    if not is_admin_or_mod(interaction.user):
        await interaction.response.send_message("❗Uh-oh! That action isn't allowed.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    await delete_birthday(str(user.id))
    await update_pinned_birthday_message(interaction.guild)
    await interaction.followup.send(f"🗑️ Birthday for {user.display_name} has been deleted.", ephemeral=True)

# /importbirthdays (admin or mod)
@bot.tree.command(name="importbirthdays", description="Admin or Mod: import birthdays from a message", guild=GUILD)
@app_commands.describe(channel="Channel containing the message", message_id="Message ID")
async def importbirthdays(interaction: discord.Interaction, channel: discord.TextChannel, message_id: str):
    if not is_admin_or_mod(interaction.user):
        await interaction.response.send_message("❗Uh-oh! That action isn't allowed.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        msg = await channel.fetch_message(int(message_id))
        lines = msg.content.splitlines()
        updated_count = 0

        async with aiosqlite.connect(DB_FILE) as db:
            for line in lines:
                if "-" not in line:
                    continue
                user_part, date_part = line.split("-", 1)
                user_part = user_part.strip()
                date_part = date_part.strip()

                # Parse user
                user_id = None
                if user_part.startswith("<@") and user_part.endswith(">"):
                    user_id = int(user_part.replace("<@", "").replace("!", "").replace(">", ""))
                else:
                    try:
                        user_id = int(user_part)
                    except ValueError:
                        continue

                # Parse date
                result = None
                if "/" in date_part:
                    try:
                        day_str, month_str = date_part.split("/", 1)
                        result = parse_day_month_input(day_str, month_str)
                    except:
                        continue
                else:
                    try:
                        day_str, month_str = date_part.split()
                        result = parse_day_month_input(day_str, month_str)
                    except:
                        continue

                if not result:
                    continue

                day, month = result
                birthday_str = f"{month:02d}-{day:02d}"

                await db.execute(
                    "INSERT INTO birthdays (user_id, birthday) VALUES (?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET birthday = excluded.birthday",
                    (str(user_id), birthday_str)
                )
                updated_count += 1
            await db.commit()

        await update_pinned_birthday_message(interaction.guild)
        await interaction.followup.send(f"✅ Imported {updated_count} birthdays and updated pinned message.", ephemeral=True)

    except discord.NotFound:
        await interaction.followup.send("🔍 Message not found or I can't see that channel. Let's try again!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"🚨 Hm… I couldn’t import the birthdays. Please try again.: {e}", ephemeral=True)

# /testbirthday
@bot.tree.command(name="testbirthday", description="Force birthday message check", guild=GUILD)
async def testbirthday(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await birthday_check(force=True)
    await interaction.followup.send("✅ Birthday check completed.", ephemeral=True)


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

# -----------------------------
# Run the bot
# -----------------------------
bot.run(TOKEN)


## todo
#
# instead of making the bot edit a message, it would be 10x easier if it just sends the list as a new message (and deletes the onld one). this can happen in a seperate thread
# set bday role to users 
#