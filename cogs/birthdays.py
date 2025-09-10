import discord
from discord import app_commands
from discord.ext import commands
from database import set_birthday, delete_birthday
from utils import parse_day_month_input, format_birthday_display, update_pinned_birthday_message
from logger import logger

class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="setbirthday",
        description="Set your birthday (day then month)"
    )
    @app_commands.describe(day="Day of birthday", month="Month of birthday")
    async def setbirthday(self, interaction: discord.Interaction, day: int, month: int):
        await interaction.response.defer(ephemeral=True)
        result = parse_day_month_input(day, month)
        if not result:
            await interaction.followup.send("❗ Invalid day/month! Example: 25 12", ephemeral=True)
            logger.warning(f"Invalid birthday input from {interaction.user} in {interaction.guild.name}")
            return

        day, month = result
        birthday_str = f"{month:02d}-{day:02d}"
        try:
            await set_birthday(str(interaction.guild.id), str(interaction.user.id), birthday_str)
            await update_pinned_birthday_message(interaction.guild)
        except Exception as e:
            logger.error(f"Error setting birthday for {interaction.user}: {e}")
            await interaction.followup.send("🚨 Failed to set birthday. Try again later.", ephemeral=True)
            return

        human_readable = format_birthday_display(birthday_str)
        logger.info(f"🎂 {interaction.user} set birthday to {human_readable} in {interaction.guild.name}")
        await interaction.followup.send(
            f"All done 💌 Your special day is marked as {human_readable}. Hugs are on the way!",
            ephemeral=True
        )

    @app_commands.command(name="deletebirthday", description="Delete your birthday")
    async def deletebirthday(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await delete_birthday(str(interaction.guild.id), str(interaction.user.id))
            await update_pinned_birthday_message(interaction.guild)
        except Exception as e:
            logger.error(f"Error deleting birthday for {interaction.user}: {e}")
            await interaction.followup.send("🚨 Failed to delete birthday. Try again later.", ephemeral=True)
            return

        logger.info(f"🗑️ {interaction.user} deleted their birthday in {interaction.guild.name}")
        await interaction.followup.send("All done 🎈 Your birthday has been deleted.", ephemeral=True)

    @app_commands.command(name="listbirthdays", description="Refresh and pin the birthday list")
    async def listbirthdays(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await update_pinned_birthday_message(interaction.guild)
        except Exception as e:
            logger.error(f"Error refreshing pinned birthday list by {interaction.user}: {e}")
            await interaction.followup.send("🚨 Failed to refresh birthday list. Try again later.", ephemeral=True)
            return

        logger.info(f"📌 {interaction.user} refreshed pinned birthday list in {interaction.guild.name}")
        await interaction.followup.send("📌 Birthday list updated and pinned!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
