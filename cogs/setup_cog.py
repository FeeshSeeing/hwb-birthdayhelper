# cogs/setup_cog.py
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from utils import update_pinned_birthday_message


DB_FILE = "birthdays.db"

class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Setup the bot for your server")
    @app_commands.describe(
        channel="Channel to post birthdays",
        birthday_role="Role to assign on birthdays",
        mod_role="Moderator role",
        check_hour="Hour to send birthday messages (0-23)"
    )
    async def setup(self, interaction: discord.Interaction,
                    channel: discord.TextChannel,
                    birthday_role: discord.Role,
                    mod_role: discord.Role = None,
                    check_hour: int = 9):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can run this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        check_hour = max(0, min(check_hour, 23))
        
        # Save config to DB
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                """
                INSERT INTO guild_config (guild_id, channel_id, birthday_role_id, mod_role_id, check_hour)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id=excluded.channel_id,
                    birthday_role_id=excluded.birthday_role_id,
                    mod_role_id=excluded.mod_role_id,
                    check_hour=excluded.check_hour
                """,
                (
                    str(interaction.guild.id),
                    str(channel.id),
                    str(birthday_role.id),
                    str(mod_role.id) if mod_role else None,
                    check_hour
                )
            )
            await db.commit()

        # Update pinned birthday message
        await update_pinned_birthday_message(interaction.guild)

        # Sync commands for this guild
        try:
            await self.bot.tree.sync(guild=interaction.guild)
        except Exception as e:
            print(f"Failed to sync commands for {interaction.guild.name}: {e}")

        await interaction.followup.send(
            f"✅ Bot configured! Birthdays will post in {channel.mention}",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
