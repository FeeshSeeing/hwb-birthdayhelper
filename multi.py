import os
import discord
from discord.ext import tasks, commands
from discord import app_commands
from dotenv import load_dotenv
import datetime
import aiosqlite
import calendar

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# -----------------------------
# Discord intents
# -----------------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Track users already wished today per guild
already_wished_today = {}

# Database file
DB_FILE = "birthdays.db"

# -----------------------------
# Database Initialization
# -----------------------------
async def init_db():
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

# -----------------------------
# Database helpers
# -----------------------------
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
            "SELECT user_id, birthday FROM birthdays WHERE guild_id=?",
            (guild_id,)
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

async def delete_birthday(guild_id: str, user_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "DELETE FROM birthdays WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )
        await db.commit()

# -----------------------------
# Utilities
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

def is_admin_or_mod(member: discord.Member, mod_role_id: int = None):
    if member.guild_permissions.administrator:
        return True
    if mod_role_id:
        return any(role.id == mod_role_id for role in member.roles)
    return False

# -----------------------------
# Pinned message helpers
# -----------------------------
async def update_pinned_birthday_message(guild: discord.Guild):
    guild_config = await get_guild_config(str(guild.id))
    if not guild_config:
        return
    channel = guild.get_channel(guild_config["channel_id"])
    if not channel:
        return
    birthdays = await get_birthdays(str(guild.id))
    if not birthdays:
        content = "📂 Oops! There are no birthdays in the database yet."
    else:
        sorted_rows = []
        for user_id_str, birthday in birthdays:
            try:
                user_id = int(user_id_str)
                member = guild.get_member(user_id)
                name = member.display_name if member else f"<@{user_id}>"
                sorted_rows.append((name.lower(), name, birthday))
            except:
                sorted_rows.append((user_id_str.lower(), user_id_str, birthday))
        sorted_rows.sort(key=lambda x: x[0])
        content = "**⋆ ˚｡⋆ BIRTHDAY LIST ⋆ ˚｡⋆🎈🎂**\n"
        for _, name, birthday in sorted_rows:
            content += f"✦ {name}: {format_birthday_display(birthday)}\n"

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT value FROM config WHERE key=?",
            (f"pinned_birthday_msg_{guild.id}",)
        ) as cursor:
            result = await cursor.fetchone()
        pinned_msg = None
        if result:
            try:
                pinned_msg = await channel.fetch_message(int(result[0]))
            except discord.NotFound:
                pinned_msg = None
        if pinned_msg:
            await pinned_msg.edit(content=content)
        else:
            pinned_msg = await channel.send(content)
            if channel.permissions_for(guild.me).manage_messages:
                await pinned_msg.pin()
        await db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (f"pinned_birthday_msg_{guild.id}", str(pinned_msg.id))
        )
        await db.commit()

# -----------------------------
# Birthday check loop
# -----------------------------
@tasks.loop(minutes=60)
async def birthday_check():
    now = datetime.datetime.now()
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT guild_id, check_hour FROM guild_config") as cursor:
            async for row in cursor:
                guild_id, check_hour = row
                if now.hour != check_hour:
                    continue
                guild = bot.get_guild(int(guild_id))
                if not guild:
                    continue
                config = await get_guild_config(guild_id)
                channel = guild.get_channel(config["channel_id"])
                if not channel:
                    continue
                today_str = now.strftime("%m-%d")
                birthdays = await get_birthdays(guild_id)
                if guild_id not in already_wished_today:
                    already_wished_today[guild_id] = set()
                for user_id, birthday in birthdays:
                    if birthday == today_str and user_id not in already_wished_today[guild_id]:
                        member = guild.get_member(int(user_id))
                        if member:
                            await channel.send(
                                f"Happy Birthday, {member.mention}! 🎈\n"
                                f"From all of us at {guild.name}, sending you lots of love today 💖🎂"
                                )
                            if config["birthday_role_id"]:
                                role = guild.get_role(config["birthday_role_id"])
                                if role and role not in member.roles:
                                    try:
                                        await member.add_roles(role, reason="Birthday!")
                                    except discord.Forbidden:
                                        await channel.send(f"⚠️ Cannot add birthday role to {member.mention}.")
                        already_wished_today[guild_id].add(user_id)

# -----------------------------
# User Commands
# -----------------------------
@bot.tree.command(name="setbirthday", description="Set your birthday (day then month)")
@app_commands.describe(day="Day of birthday", month="Month of birthday")
async def setbirthday(interaction: discord.Interaction, day: int, month: int):
    await interaction.response.defer(ephemeral=True)
    result = parse_day_month_input(day, month)
    if not result:
        await interaction.followup.send("❗Invalid day/month! Example: 25 12", ephemeral=True)
        return
    day, month = result
    birthday_str = f"{month:02d}-{day:02d}"
    await set_birthday(str(interaction.guild.id), str(interaction.user.id), birthday_str)
    await update_pinned_birthday_message(interaction.guild)
    human_readable = format_birthday_display(birthday_str)
    await interaction.followup.send(
        f"All done 💌 Your special day is marked as {human_readable}. Hugs are on the way!",
        ephemeral=True
    )

@bot.tree.command(name="deletebirthday", description="Delete your birthday")
async def deletebirthday(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await delete_birthday(str(interaction.guild.id), str(interaction.user.id))
    await update_pinned_birthday_message(interaction.guild)
    await interaction.followup.send("All done 🎈 Your birthday has been deleted.", ephemeral=True)

@bot.tree.command(name="listbirthdays", description="List all birthdays in this server")
async def listbirthdays(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await update_pinned_birthday_message(interaction.guild)
    await interaction.followup.send("📌 Birthday list updated and pinned for everyone!", ephemeral=True)

# -----------------------------
# Admin / Mod Commands
# -----------------------------
@bot.tree.command(name="setuserbirthday", description="Set birthday for another user (Admin/Mod)")
@app_commands.describe(user="User", day="Day", month="Month")
async def setuserbirthday(interaction: discord.Interaction, user: discord.Member, day: int, month: int):
    guild_config = await get_guild_config(str(interaction.guild.id))
    if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
        await interaction.response.send_message("❗You are not allowed to use this.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    result = parse_day_month_input(day, month)
    if not result:
        await interaction.followup.send("❗Invalid day/month!", ephemeral=True)
        return
    day, month = result
    birthday_str = f"{month:02d}-{day:02d}"
    await set_birthday(str(interaction.guild.id), str(user.id), birthday_str)
    await update_pinned_birthday_message(interaction.guild)
    human_readable = format_birthday_display(birthday_str)
    await interaction.followup.send(f"💌 {user.display_name}'s birthday is set to {human_readable}.", ephemeral=True)

@bot.tree.command(name="deleteuserbirthday", description="Delete birthday for another user (Admin/Mod)")
@app_commands.describe(user="User")
async def deleteuserbirthday(interaction: discord.Interaction, user: discord.Member):
    guild_config = await get_guild_config(str(interaction.guild.id))
    if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
        await interaction.response.send_message("❗You are not allowed to use this.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await delete_birthday(str(interaction.guild.id), str(user.id))
    await update_pinned_birthday_message(interaction.guild)
    await interaction.followup.send(f"🗑️ {user.display_name}'s birthday has been deleted.", ephemeral=True)

@bot.tree.command(name="importbirthdays", description="Import birthdays from a message (Admin/Mod)")
@app_commands.describe(channel="Channel containing the message", message_id="Message ID")
async def importbirthdays(interaction: discord.Interaction, channel: discord.TextChannel, message_id: str):
    guild_config = await get_guild_config(str(interaction.guild.id))
    if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
        await interaction.response.send_message("❗You are not allowed to use this.", ephemeral=True)
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

                # Parse user ID
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
                    "INSERT OR REPLACE INTO birthdays (guild_id, user_id, birthday) VALUES (?, ?, ?)",
                    (str(interaction.guild.id), str(user_id), birthday_str)
                )
                updated_count += 1
            await db.commit()
        await update_pinned_birthday_message(interaction.guild)
        await interaction.followup.send(f"✅ Imported {updated_count} birthdays and updated pinned message.", ephemeral=True)
    except discord.NotFound:
        await interaction.followup.send("🔍 Message not found or I can't access that channel.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"🚨 Error importing birthdays: {e}", ephemeral=True)

@bot.tree.command(name="exportbirthdays", description="Export birthdays to a text file")
async def exportbirthdays(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    birthdays = await get_birthdays(str(interaction.guild.id))
    if not birthdays:
        await interaction.followup.send("No birthdays found for this server.", ephemeral=True)
        return
    lines = []
    for user_id, birthday in birthdays:
        member = interaction.guild.get_member(int(user_id))
        name = member.display_name if member else f"<@{user_id}>"
        lines.append(f"{name} - {birthday}")
    file_content = "\n".join(lines)
    file_name = f"birthdays_{interaction.guild.id}.txt"
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(file_content)
    await interaction.followup.send(file=discord.File(file_name), ephemeral=True)

@bot.tree.command(name="testbirthday", description="Force birthday message check")
async def testbirthday(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await birthday_check()
    await interaction.followup.send("✅ Birthday check completed.", ephemeral=True)

# -----------------------------
# Setup command with guild sync
# -----------------------------
@bot.tree.command(name="setup", description="Setup the bot for your server")
@app_commands.describe(
    channel="Channel to post birthdays",
    birthday_role="Role to assign on birthdays",
    mod_role="Moderator role",
    check_hour="Hour to send birthday messages (0-23)"
)
async def setup(interaction: discord.Interaction,
                channel: discord.TextChannel,
                birthday_role: discord.Role,
                mod_role: discord.Role = None,
                check_hour: int = 9):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can run this.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO guild_config (guild_id, channel_id, birthday_role_id, mod_role_id, check_hour)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id=excluded.channel_id,
                birthday_role_id=excluded.birthday_role_id,
                mod_role_id=excluded.mod_role_id,
                check_hour=excluded.check_hour
            """,
            (str(interaction.guild.id),
             str(channel.id),
             str(birthday_role.id),
             str(mod_role.id) if mod_role else None,
             check_hour)
        )
        await db.commit()
    await update_pinned_birthday_message(interaction.guild)
    # Sync commands for this guild immediately
    try:
        await bot.tree.sync(guild=interaction.guild)
    except Exception as e:
        print(f"Failed to sync commands for {interaction.guild.name}: {e}")
    await interaction.followup.send(f"✅ Bot configured! Birthdays will post in {channel.mention}", ephemeral=True)

# -----------------------------
# Events
# -----------------------------
@bot.event
async def on_guild_join(guild: discord.Guild):
    default_channel = next(
        (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
        None
    )
    if default_channel:
        await default_channel.send(
            "👋 Hello! Thanks for inviting me! Run `/setup` to configure the bot."
        )
    # Sync commands for this guild
    try:
        await bot.tree.sync(guild=guild)
    except Exception as e:
        print(f"Failed to sync commands for {guild.name}: {e}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await init_db()
    birthday_check.start()
    # Sync commands for all guilds
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=guild)
            print(f"Commands synced for {guild.name}")
        except Exception as e:
            print(f"Failed to sync commands for {guild.name}: {e}")

# -----------------------------
# Run bot
# -----------------------------
bot.run(TOKEN)
