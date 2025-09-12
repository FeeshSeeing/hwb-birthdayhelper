import discord
from discord import app_commands
from discord.ext import commands
from tasks import run_birthday_check_once
from database import get_guild_config
from utils import logger, parse_day_month_input
import datetime as dt

def is_admin_or_mod(member: discord.Member, mod_role_id: int | None = None) -> bool:
    """Check if a member is an administrator or has the optional moderator role."""
    if member.guild_permissions.administrator:
        return True
    if mod_role_id:
        for role in member.roles:
            if role.id == mod_role_id:
                return True
    return False

class TestDateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="testdate",
        description="Force birthday check for a specific date (Admin/Mod)"
    )
    @app_commands.describe(
        day="Day of the month",
        month="Month number (1-12)"
    )
    async def testdate(self, interaction: discord.Interaction, day: int, month: int):
        guild_config = await get_guild_config(str(interaction.guild.id))
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            logger.warning(f"{interaction.user} attempted unauthorized /testdate in {interaction.guild.name}")
            return

        await interaction.response.defer(ephemeral=True)

        result = parse_day_month_input(day, month)
        if not result:
            await interaction.followup.send("❗ Invalid day/month!", ephemeral=True)
            return
        day, month = result

        # Create a datetime object for the test date in GMT+0
        today = dt.datetime.now(dt.timezone.utc)
        test_date = dt.datetime(year=today.year, month=month, day=day, tzinfo=dt.timezone.utc)

        try:
            await run_birthday_check_once(self.bot, test_date=test_date)
            await interaction.followup.send(f"✅ Birthday check completed for {day:02d}-{month:02d} (GMT+0).", ephemeral=True)
            logger.info(f"{interaction.user} ran /testdate for {day:02d}-{month:02d} in {interaction.guild.name}")
        except Exception as e:
            await interaction.followup.send(f"🚨 Error running testdate: {e}", ephemeral=True)
            logger.error(f"Error running /testdate: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(TestDateCog(bot))
