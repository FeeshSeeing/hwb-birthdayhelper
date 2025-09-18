# cogs/member_cleanup.py
import discord
from discord.ext import commands
from utils import update_pinned_birthday_message
from logger import logger

class MemberCleanup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild_id = member.guild.id
        user_id = member.id
        try:
            # Delete the birthday from DB using persistent connection
            await self.bot.db.delete_birthday(guild_id, user_id)

            # Refresh pinned birthday message (pass db!)
            await update_pinned_birthday_message(member.guild, db=self.bot.db)
            logger.info(
                f"👋 Removed {member.display_name}'s birthday because they left the server and refreshed pinned message in {member.guild.name}"
            )
        except Exception as e:
            logger.error(
                f"🚨 Error removing birthday for {member.display_name} in {member.guild.name}: {e}",
                exc_info=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(MemberCleanup(bot))
