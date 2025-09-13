import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import init_db
from logger import logger
from tasks import birthday_check_loop
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN is None:
    raise RuntimeError("DISCORD_TOKEN is not set in environment variables.")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user}")

    # Initialize database and background task
    await init_db()
    bot.loop.create_task(birthday_check_loop(bot))

    await asyncio.sleep(1)

    for guild in bot.guilds:
        if guild is None:
            continue  # skip invalid guilds
        try:
            # Clear old commands safely
            bot.tree.clear_commands(guild=guild) # <- remove after first successful sync
            logger.info(f"🗑️ Cleared old commands for {guild.name}")

            # Sync new commands
            await bot.tree.sync(guild=guild)
            logger.info(f"🔄 Synced new commands for {guild.name}")

        except Exception as e:
            logger.error(f"Failed to sync commands for {guild.name}: {e}")

    # sync globally (optional, slower to propagate)
    try:
        await bot.tree.sync()
        logger.info("🌐 Global command sync complete")
    except Exception as e:
        logger.error(f"Failed to sync global commands: {e}")

async def load_cogs():
    await bot.load_extension("cogs.setup_cog")
    await bot.load_extension("cogs.birthdays")
    await bot.load_extension("cogs.admin")
    await bot.load_extension("cogs.testdate")
    await bot.load_extension("cogs.birthdaylist")  # new paginated command

@bot.event
async def on_guild_join(guild: discord.Guild):
    from database import get_guild_config
    config = await get_guild_config(str(guild.id))
    channel = guild.get_channel(config["channel_id"]) if config and config.get("channel_id") else guild.system_channel
    if channel:
        try:
            await channel.send(
                "👋 Hello! Thanks for inviting me! Run /setup to configure the bot."
            )
        except discord.Forbidden:
            print(f"Cannot send welcome message in {guild.name}")

async def main():
    await load_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped manually.")
