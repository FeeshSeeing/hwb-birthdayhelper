import discord
from discord import app_commands
from discord.ext import commands
from tasks import run_birthday_check_once, already_wished_today
from logger import logger

class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="testbirthday", description="Force birthday message check")
    async def testbirthday(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            already_wished_today.clear()
            await run_birthday_check_once(self.bot)
            await interaction.followup.send(
                "✅ Birthday check completed and tracker reset.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Test birthday command failed: {e}")
            await interaction.followup.send(
                f"🚨 Birthday check failed: {e}", ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(TestCog(bot))
