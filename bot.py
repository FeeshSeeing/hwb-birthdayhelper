import discord
from discord.ext import commands
import asyncio
import logging
from config import BOT_TOKEN, GUILD_IDS, BIRTHDAY_INTERVAL_MINUTES, DB_FILE
from database import Database
from logger import logger
from tasks import birthday_check_loop

# --- Intents ---
intents = discord.Intents.default()
intents.members = True  # Needed to access member info for birthdays

# --- Cogs to Load ---
COGS_TO_LOAD = [
    "cogs.birthdays",
    "cogs.admin",
    "cogs.setup_cog",
    "cogs.testdate",
    "cogs.debug_cog",
    "cogs.member_cleanup",
    "cogs.help"
]

class BirthdayBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database(DB_FILE)  # Single persistent DB instance
        self.birthday_task = None

    async def setup_hook(self):
        """This runs once when the bot starts — perfect place for setup."""
        logger.info("--- Starting Setup ---")

        # 1. Initialize Database
        await self.db.connect()
        await self.db.init_db()
        logger.info("✅ Database initialized.")

        # 2. Load Cogs
        for cog in COGS_TO_LOAD:
            try:
                await self.load_extension(cog)
                logger.info(f"-> Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"-> Failed to load cog {cog}: {e}")
        logger.info("✅ All cogs loaded.")

        # 3. Sync Slash Commands
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
            logger.error(f"Error syncing commands: {e}", exc_info=True)

        # 4. Start Birthday Loop
        self.start_birthday_loop()
        logger.info("✅ Setup complete.")

    def start_birthday_loop(self):
        """Starts the birthday check background task."""
        if self.birthday_task is None or self.birthday_task.done():
            logger.info("🕒 Scheduling birthday check loop...")
            self.birthday_task = asyncio.create_task(self.safe_birthday_loop())

    async def safe_birthday_loop(self):
        """Wrapper for the birthday loop that restarts it on crash."""
        await self.wait_until_ready()
        await asyncio.sleep(2)  # Allow member cache to populate
        while not self.is_closed():
            try:
                await birthday_check_loop(self, interval_minutes=BIRTHDAY_INTERVAL_MINUTES)
            except Exception as e:
                logger.error(f"❌ Birthday check loop crashed: {e}", exc_info=True)
                logger.info("🔁 Restarting birthday check loop in 60 seconds...")
                await asyncio.sleep(60)

    async def close(self):
        """Ensure DB is closed properly when the bot shuts down."""
        logger.info("🔌 Shutting down bot, closing database connection...")
        await self.db.close()
        await super().close()

    async def on_ready(self):
        """Fired when bot is fully ready."""
        guild_names = ", ".join([g.name for g in self.guilds])
        logger.info("=" * 50)
        logger.info(f"✅ Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"🎉 Serving guilds: {guild_names if guild_names else 'No guilds connected'}")
        logger.info("=" * 50)

    async def on_connect(self):
        logger.info("🔌 Connected to Discord Gateway.")

    async def on_disconnect(self):
        logger.warning("⚠️ Disconnected from Discord Gateway. Attempting to reconnect...")

    async def on_resumed(self):
        logger.info("🔄 Successfully resumed session with Discord (no data loss).")


# --- Main Entry Point ---
async def main():
    bot = BirthdayBot()
    async with bot:
        await bot.start(BOT_TOKEN)

# --- Run Bot ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
