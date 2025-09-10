# cogs/test.py
import discord
from discord import app_commands
from discord.ext import commands
from tasks import run_birthday_check_once, already_wished_today  # use the new helper

class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="testbirthday", description="Force birthday message check")
    async def testbirthday(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Reset the tracker so everyone can be wished again
        already_wished_today.clear()

        # Run the birthday check safely once
        await run_birthday_check_once(self.bot)

        await interaction.followup.send(
            "✅ Birthday check completed and tracker reset.",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(TestCog(bot))
