import discord
from discord import app_commands
from discord.ext import commands
from database import set_birthday, delete_birthday, get_guild_config, get_birthdays # Added get_birthdays
from config import DB_FILE # Corrected DB_FILE import source
from utils import parse_day_month_input, format_birthday_display, update_pinned_birthday_message, is_birthday_on_date # Added is_birthday_on_date
from logger import logger
import aiosqlite
import datetime as dt # Added for is_birthday_on_date

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
    """Ensures the bot has been set up for the guild."""
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
            birthdays_today = [
                uid for uid, bday in all_birthdays_in_guild
                if is_birthday_on_date(bday, today)
            ]
            await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
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
            
            # Update pinned message with today's highlights
            all_birthdays_in_guild = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [
                uid for uid, bday in all_birthdays_in_guild
                if is_birthday_on_date(bday, today)
            ]
            await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
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
                        logger.debug(f"Skipping malformed line in import: '{line}' (missing '-')")
                        continue

                    user_id = None
                    if user_part.startswith("<@") and user_part.endswith(">"):
                        user_id = int(user_part.replace("<@", "").replace("!", "").replace(">", ""))
                    else:
                        try:
                            user_id = int(user_part)
                        except ValueError:
                            logger.debug(f"Skipping line: User ID '{user_part}' not a valid ID in '{line}'")
                            continue

                    day_str, month_str = None, None
                    try:
                        if "/" in date_part:
                            day_str, month_str = date_part.split("/", 1)
                        elif " " in date_part:
                            day_str, month_str = date_part.split(" ", 1)
                        else:
                            logger.debug(f"Skipping line: Date part '{date_part}' in '{line}' is not in DD/MM or DD MM format.")
                            continue
                        
                        result = parse_day_month_input(day_str, month_str)
                    except ValueError:
                        logger.debug(f"Skipping line: Date part '{date_part}' in '{line}' could not be parsed.")
                        continue

                    if not result:
                        logger.debug(f"Skipping line: Parsed day/month '{day_str} {month_str}' is invalid in '{line}'.")
                        continue

                    day, month = result
                    birthday_str = f"{month:02d}-{day:02d}"
                    await db.execute(
                        "INSERT OR REPLACE INTO birthdays (guild_id, user_id, birthday) VALUES (?, ?, ?)",
                        (str(interaction.guild.id), str(user_id), birthday_str)
                    )
                    updated_count += 1
                await db.commit()

            # Update pinned message with today's highlights after import
            all_birthdays_in_guild = await get_birthdays(str(interaction.guild.id))
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [
                uid for uid, bday in all_birthdays_in_guild
                if is_birthday_on_date(bday, today)
            ]
            await update_pinned_birthday_message(interaction.guild, highlight_today=birthdays_today)
            logger.info(f"📥 Imported {updated_count} birthdays in {interaction.guild.id} by {interaction.user.id}")
            await interaction.followup.send(f"✅ Imported {updated_count} birthdays and updated pinned message.", ephemeral=True)

        except discord.NotFound:
            logger.warning(f"Import failed: Message ID '{message_id}' not found or inaccessible in channel {channel.id} in guild {interaction.guild.id} by {interaction.user.id}.")
            await interaction.followup.send("🔍 Message not found or I can't access that channel.", ephemeral=True)
        except discord.Forbidden:
            logger.warning(f"Import failed: Bot lacks permissions to read message ID '{message_id}' in channel {channel.id} in guild {interaction.guild.id} by {interaction.user.id}.")
            await interaction.followup.send("🚫 I don't have permission to read messages in that channel.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error importing birthdays for guild {interaction.guild.id} by {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send(f"🚨 Error importing birthdays: {e}", ephemeral=True)

    @app_commands.command(name="wipeguild", description="Completely wipe all birthdays and config for this server (Admin/Mod)")
    async def wipeguild(self, interaction: discord.Interaction):
        guild_config = await get_guild_config(str(interaction.guild.id))
        if not guild_config or not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            logger.warning(f"Unauthorized access: {interaction.user.id} attempted wipeguild in {interaction.guild.id}")
            return

        await interaction.response.send_message(
            "⚠️ **This will erase ALL birthdays and settings for this server.**\n"
            "Type `YES` to confirm within 15 seconds.", ephemeral=True
        )

        def check(message: discord.Message):
            return (
                message.author == interaction.user
                and message.channel == interaction.channel
                and message.content.strip().upper() == "YES"
            )

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=15)
        except TimeoutError:
            await interaction.followup.send("⏳ Wipe cancelled — no confirmation received.", ephemeral=True)
            logger.info(f"Guild wipe cancelled by timeout for {interaction.guild.id} by {interaction.user.id}")
            return

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM guild_config WHERE guild_id=?", (str(interaction.guild.id),))
            await db.execute("DELETE FROM birthdays WHERE guild_id=?", (str(interaction.guild.id),))
            await db.execute("DELETE FROM config WHERE key=?", (f"pinned_birthday_msg_{interaction.guild.id}",))
            await db.commit()

        logger.warning(f"🧹 Wiped all data for guild {interaction.guild.name} ({interaction.guild.id}) by {interaction.user.id}")
        await interaction.followup.send("✅ All data wiped. Please run `/setup` again to reconfigure.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))