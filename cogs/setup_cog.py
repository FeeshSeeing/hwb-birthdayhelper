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

    @app_commands.command(
        name="setup",
        description="Setup the bot for your server"
    )
    @app_commands.describe(
        channel="Channel to post birthdays",
        birthday_role="Role to assign on birthdays (optional)",
        mod_role="Moderator role (optional, only admins otherwise)",
        check_hour="Hour to send birthday messages (0-23, GMT+0)(Default 9:00)"
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        birthday_role: discord.Role = None,
        mod_role: discord.Role = None,
        check_hour: int = 9
    ):
        # Clamp check_hour to valid range
        check_hour = max(0, min(check_hour, 23))

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❗ You are not allowed to use this.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

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
                    str(birthday_role.id) if birthday_role else None,
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

        # Send clear confirmation message
        confirmation_lines = [
            "✅ HWB-BirthdayHelper is now configured!",
            f"Birthdays will post in {channel.mention} at {check_hour}:00 GMT+0.",
            f"{'Birthday role: ' + birthday_role.mention if birthday_role else 'No birthday role set.'}",
            f"{'Moderator role: ' + mod_role.mention if mod_role else 'Admin-only for mod commands.'}"
        ]
        if birthday_role:
            confirmation_lines.append(
                "⚠️ Make sure HWB-BirthdayHelper's bot role is higher than the birthday role "
                "in the server role hierarchy, otherwise it cannot assign it."
            )

        await interaction.followup.send("\n".join(confirmation_lines), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
