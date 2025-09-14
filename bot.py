# bot.py

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import init_db, get_guild_config
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

    bot.loop.create_task(birthday_check_loop(bot))
    logger.info("Started background birthday check loop.")

    logger.info("Attempting to synchronize commands...")

    # --- START TEMPORARY AGGRESSIVE COMMAND CLEAR (FOR ONE RUN ONLY) ---
    logger.warning("ATTENTION: AGGRESSIVELY CLEARING ALL GLOBAL AND GUILD COMMANDS. THIS IS FOR DEBUGGING DUPLICATES AND MUST BE REMOVED AFTER ONE SUCCESSFUL RUN.")
    
    # 1. Clear all global commands
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync() # Sync to apply the global clear
    logger.info("Global commands cleared and synced.")

    # 2. Clear all guild commands for each guild
    for guild in bot.guilds:
        if guild is None:
            continue
        try:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild) # Sync to apply the guild clear
            logger.info(f"Commands cleared and synced for guild: {guild.name} (ID: {guild.id})")
        except discord.Forbidden:
            logger.warning(f"Bot lacks permissions to clear/sync commands for guild {guild.name} (ID: {guild.id}).")
        except Exception as e:
            logger.error(f"Failed to clear/sync commands for guild {guild.name} (ID: {guild.id}): {e}", exc_info=True)
            
    logger.warning("All commands cleared. Now attempting to re-sync all commands from scratch.")
    # --- END TEMPORARY AGGRESSIVE COMMAND CLEAR ---

    # Now, re-sync all commands properly
    # This ensures global commands are copied to all guilds and then all are synced.
    for guild in bot.guilds:
        if guild is None:
            continue
        try:
            bot.tree.copy_global_to(guild=guild) # Copy global commands to this guild's command tree
            await bot.tree.sync(guild=guild) # Sync this specific guild's commands
            logger.info(f"🔄 Re-synced commands for guild: {guild.name} (ID: {guild.id})")
        except discord.Forbidden:
            logger.warning(f"Bot lacks permissions to re-sync commands for guild {guild.name} (ID: {guild.id}).")
        except Exception as e:
            logger.error(f"Failed to re-sync commands for guild {guild.name} (ID: {guild.id}): {e}", exc_info=True)

    # A final global sync for any truly global-only commands
    try:
        await bot.tree.sync()
        logger.info("🌐 Final global command re-sync complete.")
    except Exception as e:
        logger.error(f"Failed to perform final global command re-sync: {e}", exc_info=True)

    logger.info("Bot is fully ready and operational!")


@bot.event
async def on_guild_join(guild: discord.Guild):
    logger.info(f"🎉 Joined new guild: {guild.name} (ID: {guild.id})")

    try:
        bot.tree.copy_global_to(guild=guild)
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