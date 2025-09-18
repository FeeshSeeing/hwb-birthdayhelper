import discord
from discord import app_commands
from discord.ext import commands
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
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        birthday_role: discord.Role = None,
        mod_role: discord.Role = None,
        check_hour: int = 9
    ):
        check_hour = max(0, min(check_hour, 23))

        # Extra safety in case of Discord desync
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❗ You are not allowed to use this.", ephemeral=True
            )
            logger.warning(
                f"Unauthorized setup attempt by {interaction.user} in {interaction.guild.name}"
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Save config via persistent DB
            await self.bot.db.set_guild_config(
                guild_id=str(interaction.guild.id),
                channel_id=str(channel.id),
                birthday_role_id=str(birthday_role.id) if birthday_role else None,
                mod_role_id=str(mod_role.id) if mod_role else None,
                check_hour=check_hour
            )

            # Highlight birthdays happening today
            birthdays = await self.bot.db.get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [
                user_id for user_id, bday in birthdays
                if is_birthday_on_date(bday, today)
            ]

            pinned_msg = await update_pinned_birthday_message(
                interaction.guild,
                db=self.bot.db,
                highlight_today=birthdays_today,
                manual=True
            )

            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                    logger.info(f"Pinned birthday message for guild {interaction.guild.name} after setup.")
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}, missing permission.")

            # Sync commands for this guild only
            try:
                await self.bot.tree.sync(guild=interaction.guild)
                logger.info(f"Commands synced for guild {interaction.guild.name}")
            except Exception as e:
                logger.error(f"Failed to sync commands for {interaction.guild.name}: {e}")

            # Confirmation message
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

            logger.info(f"Bot setup completed by {interaction.user} in {interaction.guild.name}")
            await interaction.followup.send("\n".join(confirmation_lines), ephemeral=True)

        except Exception as e:
            logger.error(f"Error during setup for {interaction.guild.name} by {interaction.user}: {e}", exc_info=True)
            await interaction.followup.send(
                "🚨 An unexpected error occurred during setup. Please try again later or check logs.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
