import discord
from discord.ext import commands
import asyncio
import logging
from config import BOT_TOKEN, GUILD_IDS, BIRTHDAY_INTERVAL_MINUTES
from database import init_db
from logger import logger
from tasks import birthday_check_loop

# --- Intents ---
# We only need member intents for user data, not message content for slash commands
intents = discord.Intents.default()
intents.members = True

# --- Cogs to Load ---
COGS_TO_LOAD = [
    "cogs.birthdays",
    "cogs.admin",
    "cogs.setup_cog",
    "cogs.testdate",
    "cogs.debug_cog",
    "cogs.member_cleanup"
]

class BirthdayBot(commands.Bot):
    def __init__(self):
        # No command_prefix is needed for a slash-command-only bot
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.birthday_task = None

    async def setup_hook(self):
        """This runs once when the bot starts, perfect for setup."""
        logger.info("--- Starting Setup ---")

        # 1. Initialize Database
        await init_db()
        logger.info("✅ Database initialized.")

        # 2. Load Cogs
        for cog in COGS_TO_LOAD:
            try:
                await self.load_extension(cog)
                logger.info(f"-> Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"-> Failed to load cog {cog}: {e}")
        logger.info("✅ All cogs loaded.")

        # 3. Sync Commands
        try:
            if GUILD_IDS:
                for guild_id in GUILD_IDS:
                    guild = self.get_guild(guild_id)
                    if guild:
                        await self.tree.sync(guild=guild)
                        logger.info(f"🌐 Synced commands for guild: {guild.name}")
            else:
                await self.tree.sync()
                logger.info("🌐 Synced commands globally.")
        except Exception as e:
            logger.error(f"Error syncing commands: {e}")

        # 4. Start Background Loop
        self.start_birthday_loop()
        logger.info("✅ Setup complete.")

    def start_birthday_loop(self):
        """Starts the birthday check background task."""
        if self.birthday_task is None or self.birthday_task.done():
            logger.info("🕒 Scheduling birthday check loop...")
            self.birthday_task = asyncio.create_task(self.safe_birthday_loop())

    async def safe_birthday_loop(self):
        """A wrapper for the birthday loop that ensures it restarts on failure."""
        await self.wait_until_ready()
        await asyncio.sleep(2) # Allow cache to populate

        while not self.is_closed():
            try:
                await birthday_check_loop(self, interval_minutes=BIRTHDAY_INTERVAL_MINUTES)
            except Exception as e:
                logger.error(f"❌ Birthday check loop crashed: {e}", exc_info=True)
                logger.info("🔁 Restarting birthday check loop in 60 seconds...")
                await asyncio.sleep(60) # Wait a bit longer before retrying to avoid spam

    async def on_ready(self):
        """Called when the bot is fully ready."""
        guild_names = ", ".join([g.name for g in self.guilds])
        logger.info("="*50)
        logger.info(f"✅ Logged in as {self.user.name}#{self.user.discriminator}")
        logger.info(f"🎉 Bot is fully ready and operational for guilds: {guild_names}")
        logger.info("="*50)

# --- Main Entry Point ---
async def main():
    bot = BirthdayBot()
    async with bot:
        await bot.start(BOT_TOKEN)

# --- Run Bot ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())