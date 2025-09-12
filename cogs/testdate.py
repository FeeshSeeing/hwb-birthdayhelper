# cogs/testdate.py
import discord
from discord import app_commands
from discord.ext import commands
from tasks import check_and_send_birthdays, already_wished_today
from database import get_guild_config
from datetime import datetime

def is_admin_or_mod(member: discord.Member, mod_role_id: int | None = None) -> bool:
    """
    Returns True if member is admin or has the mod role (if defined)
    """
    if member.guild_permissions.administrator:
        return True
    if mod_role_id:
        for role in member.roles:
            if role.id == mod_role_id:
                return True
    return False

class TestDateCog(commands.Cog):
    """Command to simulate birthday messages for a specific date (GMT+0). Admin or Mod only."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="testdate",
        description="Simulate birthday messages for a specific date (GMT+0)."
    )
    @app_commands.describe(
        day="Day to simulate (1-31)",
        month="Month to simulate (1-12)",
        year="Optional year (default current year)"
    )
    async def testdate(
        self,
        interaction: discord.Interaction,
        day: int,
        month: int,
        year: int = None
    ):
        guild_config = await get_guild_config(str(interaction.guild.id))
        mod_role_id = guild_config.get("mod_role_id") if guild_config else None

        if not is_admin_or_mod(interaction.user, mod_role_id):
            await interaction.response.send_message(
                "❌ You are not allowed to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Use provided year or current year
        now = datetime.utcnow()
        year = year or now.year

        # Validate date
        try:
            test_date = datetime(year=year, month=month, day=day)
        except ValueError:
            await interaction.followup.send("❗ Invalid date!", ephemeral=True)
            return

        # Reset tracker so everyone can be wished again
        already_wished_today.clear()

        # Run birthday check for all guilds using the test date
        for guild in self.bot.guilds:
            await check_and_send_birthdays(guild, test_date=test_date)

        await interaction.followup.send(
            f"✅ Birthday check simulated for {test_date.strftime('%d-%m-%Y')}",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(TestDateCog(bot))
