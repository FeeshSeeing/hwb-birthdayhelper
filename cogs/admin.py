import discord
from discord import app_commands
from discord.ext import commands
from database import set_birthday, delete_birthday, get_guild_config, get_birthdays
from config import DB_FILE
from utils import parse_day_month_input, format_birthday_display, update_pinned_birthday_message, is_birthday_on_date
from logger import logger
import aiosqlite
import datetime as dt

def is_admin_or_mod(member: discord.Member, mod_role_id: int | None = None) -> bool:
    """Checks if a member has administrator permissions or the configured moderator role."""
    if member.guild_permissions.administrator:
        return True
    if mod_role_id:
        for role in member.roles:
            if role.id == mod_role_id:
                return True
    return False

async def ensure_setup(interaction: discord.Interaction) -> bool:
    guild_config = await get_guild_config(str(interaction.guild.id))
    if not guild_config:
        await interaction.response.send_message(
            "❗ Please run `/setup` first to configure HWB-BirthdayHelper for this server!",
            ephemeral=True
        )
        return False
    return True

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setuserbirthday", description="Set a birthday for another user (Admin/Mod)")
    @app_commands.describe(user="User", day="Day", month="Month")
    async def setuserbirthday(self, interaction: discord.Interaction, user: discord.Member, day: int, month: int):
        if not await ensure_setup(interaction):
            return

        guild_config = await get_guild_config(str(interaction.guild.id))
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            logger.warning(f"Unauthorized access: {interaction.user.id} attempted setuserbirthday in {interaction.guild.id}")
            return

        await interaction.response.defer(ephemeral=True)
        result = parse_day_month_input(day, month)
        if not result:
            await interaction.followup.send("❗ Invalid day/month!", ephemeral=True)
            logger.warning(f"Invalid birthday input '{day} {month}' from {interaction.user.id} for user {user.id} in {interaction.guild.id}")
            return

        day, month = result
        birthday_str = f"{month:02d}-{day:02d}"
        
        try:
            await set_birthday(str(interaction.guild.id), str(user.id), birthday_str)

            # Update pinned message with today's highlights
            all_birthdays_in_guild = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [uid for uid, bday in all_birthdays_in_guild if is_birthday_on_date(bday, today)]
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)

            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                    logger.info(f"Pinned birthday message for guild {interaction.guild.name} after admin setuserbirthday.")
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}, missing permission.")

        except Exception as e:
            logger.error(f"Error setting birthday for user {user.id} by {interaction.user.id} in {interaction.guild.id}: {e}")
            await interaction.followup.send("🚨 Failed to set user's birthday. Try again later.", ephemeral=True)
            return

        logger.info(f"👑 {interaction.user.id} set {user.id}'s birthday to {birthday_str} in {interaction.guild.id}")
        await interaction.followup.send(f"💌 {user.display_name}'s birthday is set to {format_birthday_display(birthday_str)}.", ephemeral=True)

    @app_commands.command(name="deleteuserbirthday", description="Delete a user's birthday (Admin/Mod)")
    @app_commands.describe(user="User")
    async def deleteuserbirthday(self, interaction: discord.Interaction, user: discord.Member):
        if not await ensure_setup(interaction):
            return

        guild_config = await get_guild_config(str(interaction.guild.id))
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            logger.warning(f"Unauthorized access: {interaction.user.id} attempted deleteuserbirthday in {interaction.guild.id}")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await delete_birthday(str(interaction.guild.id), str(user.id))

            # Update pinned message
            all_birthdays_in_guild = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [uid for uid, bday in all_birthdays_in_guild if is_birthday_on_date(bday, today)]
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)

            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                    logger.info(f"Pinned birthday message for guild {interaction.guild.name} after admin deleteuserbirthday.")
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}, missing permission.")

        except Exception as e:
            logger.error(f"Error deleting birthday for user {user.id} by {interaction.user.id} in {interaction.guild.id}: {e}")
            await interaction.followup.send("🚨 Failed to delete user's birthday. Try again later.", ephemeral=True)
            return

        logger.info(f"👑 {interaction.user.id} deleted {user.id}'s birthday in {interaction.guild.id}")
        await interaction.followup.send(f"🗑️ {user.display_name}'s birthday has been deleted.", ephemeral=True)

    @app_commands.command(name="importbirthdays", description="Import birthdays from a message (Admin/Mod)")
    async def importbirthdays(self, interaction: discord.Interaction, channel: discord.TextChannel, message_id: str):
        if not await ensure_setup(interaction):
            return

        guild_config = await get_guild_config(str(interaction.guild.id))
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            logger.warning(f"Unauthorized access: {interaction.user.id} attempted importbirthdays in {interaction.guild.id}")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            msg = await channel.fetch_message(int(message_id))
            lines = msg.content.splitlines()
            updated_count = 0
            async with aiosqlite.connect(DB_FILE) as db:
                for line in lines:
                    line = line.strip()
                    if not line or "-" not in line:
                        continue
                    try:
                        user_part, date_part = line.split("-", 1)
                        user_part = user_part.strip()
                        date_part = date_part.strip()
                    except ValueError:
                        logger.debug(f"Skipping malformed line: {line}")
                        continue

                    user_id = None
                    if user_part.startswith("<@") and user_part.endswith(">"):
                        user_id = int(user_part.replace("<@", "").replace("!", "").replace(">", ""))
                    else:
                        try:
                            user_id = int(user_part)
                        except ValueError:
                            continue

                    result = parse_day_month_input(*date_part.replace("/", " ").split())
                    if not result:
                        continue
                    day, month = result
                    birthday_str = f"{month:02d}-{day:02d}"
                    await db.execute(
                        "INSERT OR REPLACE INTO birthdays (guild_id, user_id, birthday) VALUES (?, ?, ?)",
                        (str(interaction.guild.id), str(user_id), birthday_str)
                    )
                    updated_count += 1
                await db.commit()

            # Update pinned message after import
            all_birthdays_in_guild = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [uid for uid, bday in all_birthdays_in_guild if is_birthday_on_date(bday, today)]
            pinned_msg = await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}, missing permission.")

            logger.info(f"📥 Imported {updated_count} birthdays in {interaction.guild.id} by {interaction.user.id}")
            await interaction.followup.send(f"✅ Imported {updated_count} birthdays and updated pinned message.", ephemeral=True)

        except discord.NotFound:
            await interaction.followup.send("🔍 Message not found or inaccessible.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("🚫 I don't have permission to read messages in that channel.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error importing birthdays for guild {interaction.guild.id} by {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send(f"🚨 Error importing birthdays: {e}", ephemeral=True)

    @app_commands.command(name="wipeguild", description="Completely wipe all birthdays and config for this server (Admin/Mod)")
    async def wipeguild(self, interaction: discord.Interaction):
        if not await ensure_setup(interaction):
            return

        guild_config = await get_guild_config(str(interaction.guild.id))
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("DELETE FROM birthdays WHERE guild_id = ?", (str(interaction.guild.id),))
                await db.execute("DELETE FROM guild_config WHERE guild_id = ?", (str(interaction.guild.id),))
                await db.commit()

            logger.info(f"🧹 {interaction.user.id} wiped guild {interaction.guild.id}")
            await interaction.followup.send("✅ Guild data wiped. Please run `/setup` again.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error wiping guild {interaction.guild.id} by {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send("🚨 Failed to wipe guild data. Try again later.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
