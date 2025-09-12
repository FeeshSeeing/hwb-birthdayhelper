import discord
from discord import app_commands
from discord.ext import commands
from database import set_birthday, delete_birthday, get_guild_config, DB_FILE
from utils import parse_day_month_input, format_birthday_display, update_pinned_birthday_message
from logger import logger
import aiosqlite

def is_admin_or_mod(member: discord.Member, mod_role_id: int | None = None) -> bool:
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
            logger.warning(f"{interaction.user} attempted unauthorized setuserbirthday in {interaction.guild.name}")
            return

        await interaction.response.defer(ephemeral=True)
        result = parse_day_month_input(day, month)
        if not result:
            await interaction.followup.send("❗ Invalid day/month!", ephemeral=True)
            return

        day, month = result
        birthday_str = f"{month:02d}-{day:02d}"
        await set_birthday(str(interaction.guild.id), str(user.id), birthday_str)
        await update_pinned_birthday_message(interaction.guild)

        logger.info(f"👑 {interaction.user} set {user}'s birthday to {birthday_str} in {interaction.guild.name}")
        await interaction.followup.send(f"💌 {user.display_name}'s birthday is set to {format_birthday_display(birthday_str)}.", ephemeral=True)

    @app_commands.command(name="deleteuserbirthday", description="Delete a user's birthday (Admin/Mod)")
    @app_commands.describe(user="User")
    async def deleteuserbirthday(self, interaction: discord.Interaction, user: discord.Member):
        if not await ensure_setup(interaction):
            return

        guild_config = await get_guild_config(str(interaction.guild.id))
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await delete_birthday(str(interaction.guild.id), str(user.id))
        await update_pinned_birthday_message(interaction.guild)

        logger.info(f"👑 {interaction.user} deleted {user}'s birthday in {interaction.guild.name}")
        await interaction.followup.send(f"🗑️ {user.display_name}'s birthday has been deleted.", ephemeral=True)

    @app_commands.command(name="importbirthdays", description="Import birthdays from a message (Admin/Mod)")
    async def importbirthdays(self, interaction: discord.Interaction, channel: discord.TextChannel, message_id: str):
        if not await ensure_setup(interaction):
            return

        guild_config = await get_guild_config(str(interaction.guild.id))
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            msg = await channel.fetch_message(int(message_id))
            lines = msg.content.splitlines()
            updated_count = 0
            async with aiosqlite.connect(DB_FILE) as db:
                for line in lines:
                    if "-" not in line:
                        continue
                    user_part, date_part = line.split("-", 1)
                    user_part = user_part.strip()
                    date_part = date_part.strip()

                    user_id = None
                    if user_part.startswith("<@") and user_part.endswith(">"):
                        user_id = int(user_part.replace("<@", "").replace("!", "").replace(">", ""))
                    else:
                        try:
                            user_id = int(user_part)
                        except ValueError:
                            continue

                    try:
                        if "/" in date_part:
                            day_str, month_str = date_part.split("/", 1)
                        else:
                            day_str, month_str = date_part.split()
                        result = parse_day_month_input(day_str, month_str)
                    except:
                        continue

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

            await update_pinned_birthday_message(interaction.guild)
            logger.info(f"📥 Imported {updated_count} birthdays in {interaction.guild.name}")
            await interaction.followup.send(f"✅ Imported {updated_count} birthdays and updated pinned message.", ephemeral=True)

        except discord.NotFound:
            await interaction.followup.send("🔍 Message not found or I can't access that channel.", ephemeral=True)
        except Exception as e:
            logger.error(f"Import error: {e}")
            await interaction.followup.send(f"🚨 Error importing birthdays: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
