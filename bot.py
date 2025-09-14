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

bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------- Load Cogs -----------------
async def load_cogs():
    cogs = ["cogs.setup_cog", "cogs.birthdays", "cogs.admin", "cogs.testdate"]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        except Exception as e:
            logger.error(f"Failed to load cog {cog}: {e}", exc_info=True)


# ----------------- Events -----------------
@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    # Start birthday background task once
    if not hasattr(bot, '_birthday_loop_started'):
        bot.loop.create_task(birthday_check_loop(bot))
        bot._birthday_loop_started = True
        logger.info("Started background birthday check loop.")

    # Sync commands globally
    try:
        await bot.tree.sync()
        logger.info("🌐 Synced all slash commands globally.")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}", exc_info=True)

    logger.info("Bot is fully ready and operational!")


@bot.event
async def on_guild_join(guild: discord.Guild):
    logger.info(f"🎉 Joined new guild: {guild.name} (ID: {guild.id})")

    try:
        await bot.tree.sync(guild=guild)
        logger.info(f"Commands synced for newly joined guild {guild.name}.")
    except discord.Forbidden:
        logger.warning(f"Bot lacks permissions to sync commands for {guild.name} (ID: {guild.id}).")
    except Exception as e:
        logger.error(f"Error syncing commands for new guild {guild.name} (ID: {guild.id}): {e}", exc_info=True)

    # Find a channel to send the welcome message
    target_channel = guild.system_channel
    if target_channel is None or not target_channel.permissions_for(guild.me).send_messages:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                target_channel = channel
                break

    if target_channel:
        try:
            await target_channel.send(
                f"👋 Hello! Thanks for inviting me to **{guild.name}**! "
                "Please have an admin run `/setup` to configure the birthday channel and roles."
            )
            logger.info(f"Sent welcome message to {target_channel.name} in {guild.name}.")
        except discord.Forbidden:
            logger.warning(f"Bot lacks permissions to send welcome message in {target_channel.name} ({target_channel.id}).")
        except Exception as e:
            logger.error(f"Error sending welcome message in {guild.name} (ID: {guild.id}): {e}", exc_info=True)
    else:
        logger.warning(f"No suitable channel to send welcome message in {guild.name} (ID: {guild.id}).")


# ----------------- Main -----------------
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
        logger.critical(f"Unexpected error during bot startup: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually by KeyboardInterrupt.")
    except RuntimeError as e:
        if "Event loop is closed" not in str(e):
            logger.critical(f"RuntimeError during bot shutdown: {e}", exc_info=True)
        else:
            logger.info("Event loop closed during shutdown (expected for KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Unhandled error outside main: {e}", exc_info=True)
