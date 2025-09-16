# bot.py
import discord
from discord.ext import commands
import asyncio
import logging
from config import BOT_TOKEN, GUILD_IDS
from database import init_db
from logger import logger
from tasks import birthday_check_loop

# -------------------- Intents --------------------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- Logging --------------------
logging.basicConfig(level=logging.INFO)
birthday_task = None  # Keep task reference
BIRTHDAY_INTERVAL = 5  # minutes

# -------------------- Startup Events --------------------
@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info("🌐 Syncing slash commands...")

    try:
        if GUILD_IDS:
            for guild_id in GUILD_IDS:
                guild = bot.get_guild(guild_id)
                if guild:
                    await bot.tree.sync(guild=guild)
                    logger.info(f"🌐 Synced commands for guild {guild.name}")
        else:
            await bot.tree.sync()
            logger.info("🌐 Synced commands globally")
    except Exception as e:
        logger.error(f"Error syncing commands: {e}")

    logger.info("🎉 Bot is fully ready and operational!")

# -------------------- Start Birthday Loop Safely --------------------
async def start_birthday_loop():
    """Wait until bot is ready, then start the birthday check loop."""
    logger.info("🕒 Scheduling birthday check loop...")
    await bot.wait_until_ready()
    logger.info(f"🕒 Starting birthday check loop (every {BIRTHDAY_INTERVAL} minutes)...")
    await asyncio.sleep(2)  # Small delay to ensure guild/member cache is populated

    global birthday_task
    if birthday_task is None or birthday_task.done():
        async def safe_birthday_loop():
            try:
                await birthday_check_loop(bot, interval_minutes=BIRTHDAY_INTERVAL)
            except Exception as e:
                logger.error(f"❌ Birthday check loop crashed: {e}", exc_info=True)
                logger.info("🔁 Restarting birthday check loop in 5 seconds...")
                await asyncio.sleep(5)

        birthday_task = asyncio.create_task(safe_birthday_loop())

# -------------------- Database Setup --------------------
async def setup_database():
    await init_db()
    logger.info("✅ Database initialized.")

# -------------------- Load Cogs --------------------
async def load_all_cogs():
    cog_list = [
        "cogs.birthdays",
        "cogs.admin",
        "cogs.setup_cog",
        "cogs.testdate",
        "cogs.debug_cog"
    ]
    for cog in cog_list:
        try:
            await bot.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        except Exception as e:
            logger.error(f"Failed to load cog {cog}: {e}")
    logger.info("✅ All cogs loaded.")

# -------------------- Main Entry Point --------------------
async def main():
    async with bot:
        # Setup database and cogs
        await setup_database()
        await load_all_cogs()

        # Start birthday loop after bot is ready
        asyncio.create_task(start_birthday_loop())

        # Start the bot
        await bot.start(BOT_TOKEN)

# -------------------- Run Bot --------------------
if __name__ == "__main__":
    asyncio.run(main())
