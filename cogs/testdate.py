# cogs/testdate.py
import discord
from discord import app_commands
from discord.ext import commands
import datetime as dt
from tasks import run_birthday_check_once
from database import get_guild_config

class TestDateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="testdate",
        description="Run a birthday check for a specific date (Admin/Mod)"
    )
    @app_commands.describe(date="Enter date in DD/MM/YYYY format")
    async def testdate(self, interaction: discord.Interaction, date: str):
        await interaction.response.defer(ephemeral=True)

        # validate format
        try:
            day_str, month_str, year_str = date.split("/")
            day, month, year = int(day_str), int(month_str), int(year_str)
        except ValueError:
            await interaction.followup.send(
                "❗ Invalid format. Use DD/MM/YYYY.", ephemeral=True
            )
            return

        # handle Feb 29 on non-leap years
        is_leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
        if month == 2 and day == 29 and not is_leap:
            await interaction.followup.send(
                "⚠ 29 Feb is not a leap year. Birthday will be checked on 28 Feb.", ephemeral=True
            )
            day = 28  # adjust to Feb 28

        try:
            test_date = dt.datetime(year, month, day, tzinfo=dt.timezone.utc)
        except ValueError:
            await interaction.followup.send(
                "❗ Invalid date. Please check day/month/year.", ephemeral=True
            )
            return

        # run birthday check only for this guild
        guild = interaction.guild
        guild_config = await get_guild_config(str(guild.id))
        if not guild_config:
            await interaction.followup.send(
                "❗ Please run /setup first to configure HWB-BirthdayHelper.", ephemeral=True
            )
            return

        await run_birthday_check_once(self.bot, guild=guild, test_date=test_date)

        await interaction.followup.send(
            f"✅ Birthday check run for {day:02d}/{month:02d}/{year}.", ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(TestDateCog(bot))
