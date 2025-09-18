import discord
from discord import app_commands
from discord.ext import commands
import datetime as dt
from tasks import run_birthday_check_once
from .admin import is_admin_or_mod  # Relative import
from logger import logger

# -------------------- Helpers --------------------
async def ensure_setup(interaction: "discord.Interaction", db) -> bool:
    """Check if the guild has a config setup."""
    guild_config = await db.get_guild_config(interaction.guild.id)
    if not guild_config:
        try:
            await interaction.response.send_message(
                "❗ Please run `/setup` first to configure HWB-BirthdayHelper for this server!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Failed to send setup prompt: {e}", exc_info=True)
        return False
    return True

# -------------------- Cog --------------------
class TestDateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="testdate",
        description="Run a birthday check for a specific date (Admin/Mod)"
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(date="Enter date in DD/MM/YYYY format")
    async def testdate(self, interaction: "discord.Interaction", date: str):
        try:
            if not await ensure_setup(interaction, self.bot.db):
                return

            guild_config = await self.bot.db.get_guild_config(interaction.guild.id)
            if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
                await interaction.response.send_message(
                    "❗ You are not allowed to use this command.", ephemeral=True
                )
                logger.warning(f"Unauthorized access: {interaction.user.id} attempted testdate in {interaction.guild.id}")
                return

            await interaction.response.defer(ephemeral=True)

            # Parse date
            try:
                day_str, month_str, year_str = date.split("/")
                day, month, year = int(day_str), int(month_str), int(year_str)
                test_date = dt.datetime(year, month, day, tzinfo=dt.timezone.utc)
            except ValueError as ve:
                if "day is out of range for month" in str(ve) and month == 2 and day == 29:
                    test_date = dt.datetime(year, 2, 28, tzinfo=dt.timezone.utc)
                    await interaction.followup.send(
                        "⚠ 29 Feb is not a leap year. Checking birthdays on 28 Feb instead.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❗ Invalid date format. Use DD/MM/YYYY.", ephemeral=True
                    )
                    logger.warning(f"Invalid date '{date}' from {interaction.user.id} in {interaction.guild.id}")
                    return
            except Exception as e:
                await interaction.followup.send(
                    "🚨 Unexpected error parsing date. Please try again.", ephemeral=True
                )
                logger.error(f"Unexpected error parsing date '{date}': {e}", exc_info=True)
                return

            # Run birthday check
            try:
                await run_birthday_check_once(
                    self.bot,
                    guild=interaction.guild,
                    test_date=test_date,
                    reset_wished=True
                )
                await interaction.followup.send(
                    f"✅ Birthday check run for {test_date.strftime('%d/%m/%Y')} (UTC). Check the birthday channel.",
                    ephemeral=True
                )
                logger.info(f"Test birthday check run for {date} in guild {interaction.guild.id} by {interaction.user.id}")
            except Exception as e:
                await interaction.followup.send(
                    f"🚨 An error occurred while running the birthday check: {e}", ephemeral=True
                )
                logger.error(f"Error running birthday check once for guild {interaction.guild.id} with date {date} by {interaction.user.id}: {e}", exc_info=True)

        except Exception as e:
            try:
                await interaction.followup.send(
                    "🚨 Unexpected error occurred. Please try again later.", ephemeral=True
                )
            except Exception:
                pass
            logger.error(f"Unhandled error in /testdate command: {e}", exc_info=True)

# -------------------- Setup --------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(TestDateCog(bot))
