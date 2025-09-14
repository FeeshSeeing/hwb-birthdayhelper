import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from config import DB_FILE
from database import get_birthdays
from utils import update_pinned_birthday_message, is_birthday_on_date
from logger import logger
import datetime as dt

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
        check_hour="Hour to send birthday messages (0-23, UTC)(Default 9:00)"
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        birthday_role: discord.Role = None,
        mod_role: discord.Role = None,
        check_hour: int = 9
    ):
        check_hour = max(0, min(check_hour, 23))

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❗ You are not allowed to use this.", ephemeral=True
            )
            logger.warning(f"Unauthorized setup attempt by {interaction.user.id} in {interaction.guild.id}")
            return

        await interaction.response.defer(ephemeral=True)

        try:
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

            # Fetch existing birthdays to properly highlight if any happen to be today on setup
            birthdays = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [
                user_id for user_id, bday in birthdays
                if is_birthday_on_date(bday, today)
            ]

            # Update pinned birthday message and ensure it is pinned
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                    logger.info(f"Pinned birthday message for guild {interaction.guild.name} after setup.")
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}, missing permission.")

            # Sync commands for this guild only
            try:
                await self.bot.tree.sync(guild=interaction.guild)
                logger.info(f"Commands synced for guild {interaction.guild.name} ({interaction.guild.id})")
            except Exception as e:
                logger.error(f"Failed to sync commands for {interaction.guild.name} ({interaction.guild.id}): {e}")

            # Send confirmation message
            confirmation_lines = [
                "✅ HWB-BirthdayHelper is now configured!",
                f"Birthdays will post in {channel.mention} at {check_hour}:00 UTC.",
                f"{'Birthday role: ' + birthday_role.mention if birthday_role else 'No birthday role set.'}",
                f"{'Moderator role: ' + mod_role.mention if mod_role else 'Admin-only for mod commands.'}"
            ]
            if birthday_role:
                confirmation_lines.append(
                    "⚠️ Make sure HWB-BirthdayHelper's bot role is higher than the birthday role "
                    "in the server role hierarchy, otherwise it cannot assign it."
                )

            logger.info(f"Bot setup completed by {interaction.user.id} in {interaction.guild.id}")
            await interaction.followup.send("\n".join(confirmation_lines), ephemeral=True)

        except Exception as e:
            logger.error(f"Error during setup for guild {interaction.guild.id} by {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send(
                "🚨 An unexpected error occurred during setup. Please try again later or check logs.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
