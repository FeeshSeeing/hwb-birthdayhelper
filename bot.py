# bot.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import logging
from config import BOT_TOKEN, GUILD_IDS  # GUILD_IDS = list of test guild IDs
from database import init_db
from logger import logger

# -------------------- Intents --------------------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- Logging --------------------
logging.basicConfig(level=logging.INFO)

# -------------------- Startup --------------------
@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info("🌐 Syncing slash commands...")
    try:
        # You can limit sync to specific guilds during testing
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

# -------------------- Initialize Database --------------------
async def setup_database():
    await init_db()

# -------------------- Load Cogs --------------------
async def load_all_cogs():
    cog_list = ["cogs.birthdays", "cogs.admin", "cogs.setup_cog", "cogs.testdate"]
    for cog in cog_list:
        try:
            await bot.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        except Exception as e:
            logger.error(f"Failed to load cog {cog}: {e}")
    logger.info("✅ All cogs loaded.")


# -------------------- Main --------------------
async def main():
    async with bot:
        await setup_database()
        await load_all_cogs()
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
