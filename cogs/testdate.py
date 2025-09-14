import discord
from discord import app_commands
from discord.ext import commands
import datetime as dt
from tasks import run_birthday_check_once
from database import get_guild_config
from .admin import is_admin_or_mod # CORRECTED: Relative import
from logger import logger

# Re-using ensure_setup from other cogs for consistency
async def ensure_setup(interaction: discord.Interaction) -> bool:
    guild_config = await get_guild_config(str(interaction.guild.id))
    if not guild_config:
        await interaction.response.send_message(
            "❗ Please run `/setup` first to configure HWB-BirthdayHelper for this server!",
            ephemeral=True
        )
        return False
    return True

class TestDateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="testdate",
        description="Run a birthday check for a specific date (Admin/Mod)"
    )
    @app_commands.describe(date="Enter date in DD/MM/YYYY format")
    async def testdate(self, interaction: discord.Interaction, date: str):
        if not await ensure_setup(interaction):
            return

        guild_config = await get_guild_config(str(interaction.guild.id))
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this command.", ephemeral=True)
            logger.warning(f"Unauthorized access: {interaction.user.id} attempted testdate in {interaction.guild.id}")
            return

        await interaction.response.defer(ephemeral=True)

        day, month, year = 0, 0, 0 # Initialize for error handling scope
        # validate format
        try:
            day_str, month_str, year_str = date.split("/")
            day, month, year = int(day_str), int(month_str), int(year_str)
        except ValueError:
            await interaction.followup.send(
                "❗ Invalid format. Use DD/MM/YYYY.", ephemeral=True
            )
            logger.warning(f"Invalid date format '{date}' from {interaction.user.id} in {interaction.guild.id}")
            return

        # Attempt to create the datetime object directly from user input.
        # The core logic (is_birthday_on_date) will handle Feb 29 adjustments.
        try:
            test_date = dt.datetime(year, month, day, tzinfo=dt.timezone.utc)
        except ValueError as e:
            # Catch specific ValueError for invalid date components (e.g., Feb 30)
            if "day is out of range for month" in str(e) and month == 2 and day == 29:
                 # Special handling for Feb 29 if it's not a leap year, as the user manual states
                 await interaction.followup.send(
                    "⚠ 29 Feb is not a leap year. Birthdays will be checked on 28 Feb (if applicable).", ephemeral=True
                )
                 # Adjust date to Feb 28 for the test.
                 # This is only for the *test date itself*, the `is_birthday_on_date` handles the comparison.
                 test_date = dt.datetime(year, 2, 28, tzinfo=dt.timezone.utc)
            else:
                await interaction.followup.send(
                    "❗ Invalid date. Please check day/month/year.", ephemeral=True
                )
                logger.warning(f"Invalid date '{date}' (ValueError: {e}) from {interaction.user.id} in {interaction.guild.id}")
                return
        except Exception as e:
            logger.error(f"Unexpected error creating test_date for '{date}' by {interaction.user.id} in {interaction.guild.id}: {e}", exc_info=True)
            await interaction.followup.send(
                "🚨 An unexpected error occurred with the date. Please try again later.", ephemeral=True
            )
            return


        # run birthday check only for this guild
        guild = interaction.guild
        # guild_config check is already handled by ensure_setup, but we need it for is_admin_or_mod
        # so this line remains, but it's guaranteed to not be None here.

        try:
            await run_birthday_check_once(self.bot, guild=guild, test_date=test_date)

            logger.info(f"Test birthday check run for {date} in guild {guild.id} by {interaction.user.id}")
            await interaction.followup.send(
                f"✅ Birthday check run for {test_date.strftime('%d/%m/%Y')} (UTC). Check the birthday channel.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error running birthday check once for guild {guild.id} with date {date} by {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send(
                f"🚨 An error occurred while running the birthday check: {e}", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(TestDateCog(bot))