import discord
from discord import app_commands
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show info about using the bot")
    async def help(self, interaction: discord.Interaction):
        help_text = (
            "**🎂 HWB Birthday Helper Commands**\n\n"

            "**👤 User Commands:**\n"
            "• `/setbirthday day month` – Set your own birthday.\n"
            "• `/deletebirthday` – Delete your own birthday.\n"
            "• `/viewbirthdays` – View upcoming birthdays.\n\n"

            "**🛡️ Admin/Mod Commands:**\n"
            "• `/setuserbirthday user day month` – Set another user's birthday.\n"
            "• `/deleteuserbirthday user` – Delete a user's birthday.\n"
            "• `/importbirthdays channel message_id` – Import birthdays from a message.\n"
            "• `/testdate DD/MM/YYYY` – Run a birthday check for a specific date.\n\n"

            "**👑 Admin-Only Commands:**\n"
            "• `/clearallbirthdays` – Remove all birthdays and reset server configuration.\n"
            "• `/setup` – Configure the server so the bot can track birthdays.\n\n"

            "💡 Tip: All commands respond ephemerally to keep things tidy.\n"
            "🎉 The bot automatically updates pinned birthday messages daily."
        )

        await interaction.response.send_message(help_text, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
