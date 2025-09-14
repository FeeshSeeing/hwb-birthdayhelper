# bot.py

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
    logger.critical("DISCORD_TOKEN is not set in environment variables. Exiting.")
    raise RuntimeError("DISCORD_TOKEN is not set in environment variables.")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Use commands.Bot for prefix commands if you have any, otherwise discord.Client is fine
# If you only use slash commands, you can simplify to discord.Client, but commands.Bot is robust.
bot = commands.Bot(command_prefix="!", intents=intents)

async def load_cogs():
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

    # Start the background task only once
    if not hasattr(bot, '_birthday_loop_started'):
        bot.loop.create_task(birthday_check_loop(bot))
        bot._birthday_loop_started = True # Mark as started
        logger.info("Started background birthday check loop.")

    logger.info("Attempting to synchronize commands...")

    # Clear all commands globally and then sync only once
    # This is a drastic but effective way to ensure no duplicates.
    # Use this if you want to completely reset the command tree.
    # Otherwise, rely on guild-specific syncing only.
    try:
        # Clear all global commands
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync() # Sync global empty tree to clear them globally
        logger.info("🌐 Cleared all global commands.")
    except Exception as e:
        logger.warning(f"Failed to clear global commands: {e}")

    # Now, iterate through guilds and sync only local (guild-specific) commands.
    # Global commands (if any are truly global, i.e., not copied) will be synced by bot.tree.sync()
    # when you have no guild specified.
    for guild in bot.guilds:
        if guild is None:
            continue
        try:
            # We don't copy_global_to here if we cleared global commands.
            # Instead, ensure commands are defined with @app_commands.guilds for guild-specific.
            # Or if you *do* want global commands, ensure your cogs define them as such.
            # If your commands are *only* intended to be guild commands, this is fine.
            await bot.tree.sync(guild=guild)
            logger.info(f"🔄 Synced commands for guild: {guild.name} (ID: {guild.id})")
        except discord.Forbidden:
            logger.warning(f"Bot lacks permissions to sync commands for guild {guild.name} (ID: {guild.id}).")
        except Exception as e:
            logger.error(f"Failed to sync commands for guild {guild.name} (ID: {guild.id}): {e}", exc_info=True)

    # After iterating all guilds, if you have any truly global commands, sync them one last time.
    # If all your commands are guild-specific (using @app_commands.guilds or copied),
    # then this global sync might not be strictly necessary for functionality
    # but it doesn't hurt.
    try:
        await bot.tree.sync() # Sync any remaining global commands
        logger.info("🌐 Final global command sync complete (for any global commands).")
    except Exception as e:
        logger.error(f"Failed to perform final global command sync: {e}", exc_info=True)

    logger.info("Bot is fully ready and operational!")

    logger.info("Clearing all old commands globally and for all guilds...")
    try:
        # Clear global commands
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        logger.info("Successfully cleared global commands.")
    except Exception as e:
        logger.error(f"Error clearing global commands: {e}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    logger.info(f"🎉 Joined new guild: {guild.name} (ID: {guild.id})")

    try:
        # For a newly joined guild, explicitly sync its commands.
        # This will include any commands that are defined as global if they haven't been copied and synced yet.
        await bot.tree.sync(guild=guild)
        logger.info(f"Commands synced for newly joined guild {guild.name}.")
    except discord.Forbidden:
        logger.warning(f"Bot lacks permissions to sync commands for newly joined guild {guild.name} (ID: {guild.id}).")
    except Exception as e:
        logger.error(f"Error syncing commands for new guild {guild.name} (ID: {guild.id}): {e}", exc_info=True)

    system_channel = guild.system_channel
    target_channel = None

    if system_channel and system_channel.permissions_for(guild.me).send_messages:
        target_channel = system_channel
    else:
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
    logger.info("Starting bot initialization...")
    await init_db()
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
        if "Event loop is closed" not in str(e):
            logger.critical(f"RuntimeError during bot shutdown: {e}", exc_info=True)
        else:
            logger.info("Event loop closed during shutdown (expected behavior for KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"An unhandled error occurred outside main: {e}", exc_info=True)