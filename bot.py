import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import init_db, get_guild_config # Moved get_guild_config import here
from logger import logger
from tasks import birthday_check_loop
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN is None:
    # Use logger for critical errors before bot starts
    logger.critical("DISCORD_TOKEN is not set in environment variables. Exiting.")
    raise RuntimeError("DISCORD_TOKEN is not set in environment variables.")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True # Required for some commands and message processing if needed

bot = commands.Bot(command_prefix="!", intents=intents)

async def load_cogs():
    """Loads all cogs into the bot."""
    # List all cog files here explicitly, or use a loop to discover them
    cogs = ["cogs.setup_cog", "cogs.birthdays", "cogs.admin", "cogs.testdate"]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        except Exception as e:
            logger.error(f"Failed to load cog {cog}: {e}", exc_info=True)


@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    # Start the background birthday check loop
    bot.loop.create_task(birthday_check_loop(bot))
    logger.info("Started background birthday check loop.")

    logger.info("Attempting to synchronize commands...")

    # Sync commands for all guilds
    for guild in bot.guilds:
        if guild is None:
            logger.warning("Skipping None guild during command sync.")
            continue
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            logger.info(f"🔄 Synced commands for guild: {guild.name} (ID: {guild.id})")
        except discord.Forbidden:
            logger.warning(f"Bot lacks permissions to sync commands for guild {guild.name} (ID: {guild.id}).")
        except Exception as e:
            logger.error(f"Failed to sync commands for guild {guild.name} (ID: {guild.id}): {e}", exc_info=True)

    # Global sync, important for non-guild specific commands or a final catch-all
    try:
        await bot.tree.sync()
        logger.info("🌐 Global command sync complete.")
    except Exception as e:
        logger.error(f"Failed to sync global commands: {e}", exc_info=True)

    logger.info("Bot is fully ready and operational!")


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Event that fires when the bot joins a new guild."""
    logger.info(f"🎉 Joined new guild: {guild.name} (ID: {guild.id})")

    # Sync commands for the newly joined guild immediately
    try:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        logger.info(f"Commands synced for newly joined guild {guild.name}.")
    except discord.Forbidden:
        logger.warning(f"Bot lacks permissions to sync commands for newly joined guild {guild.name} (ID: {guild.id}).")
    except Exception as e:
        logger.error(f"Error syncing commands for new guild {guild.name} (ID: {guild.id}): {e}", exc_info=True)


    # Send a welcome message to the system channel or the first available text channel
    # When bot first joins, get_guild_config will almost certainly be empty.
    system_channel = guild.system_channel
    target_channel = None

    if system_channel and system_channel.permissions_for(guild.me).send_messages:
        target_channel = system_channel
    else:
        # Fallback to the first text channel where the bot can send messages
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                target_channel = channel
                break

    if target_channel:
        try:
            await target_channel.send(
                f"👋 Hello! Thanks for inviting me to **{guild.name}**! "
                "To get started, please have an admin run `/setup` to configure the birthday channel and roles."
            )
            logger.info(f"Sent welcome message to {target_channel.name} in {guild.name}.")
        except discord.Forbidden:
            logger.warning(f"Bot lacks permissions to send welcome message in {target_channel.name} ({target_channel.id}) in guild {guild.name}.")
        except Exception as e:
            logger.error(f"Error sending welcome message in {guild.name} (ID: {guild.id}): {e}", exc_info=True)
    else:
        logger.warning(f"Could not find any suitable channel to send welcome message in guild {guild.name} (ID: {guild.id}).")


async def main():
    """Main function to initialize the database, load cogs, and start the bot."""
    logger.info("Starting bot initialization...")
    await init_db() # Initialize DB once before loading cogs or starting tasks
    logger.info("Database initialized.")

    await load_cogs()
    logger.info("All cogs loaded.")

    try:
        await bot.start(TOKEN)
    except discord.LoginFailure:
        logger.critical("Bot failed to log in. Check your DISCORD_TOKEN.")
    except discord.HTTPException as e:
        logger.critical(f"HTTPException during bot start: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"An unexpected error occurred during bot startup: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually by KeyboardInterrupt.")
    except RuntimeError as e:
        # Catch RuntimeError for event loop closing issues, common during forced exits
        if "Event loop is closed" not in str(e):
            logger.critical(f"RuntimeError during bot shutdown: {e}", exc_info=True)
        else:
            logger.info("Event loop closed during shutdown (expected behavior for KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"An unhandled error occurred outside main: {e}", exc_info=True)