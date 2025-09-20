import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from utils import parse_day_month_input, format_birthday_display, update_pinned_birthday_message, is_birthday_on_date
from logger import logger
import datetime as dt
BOT_BIRTHDAY = 9  # September 9th, for fun message

# ---------------- Admin/Mod Utilities ----------------
def is_admin_or_mod(member: discord.Member, mod_role_id: int | str | None = None) -> bool:
    """Check if a member has administrator permissions or the configured moderator role."""
    if member.guild_permissions.administrator:
        return True
    if mod_role_id:
        try:
            mod_role_id = int(mod_role_id)
        except (TypeError, ValueError):
            return False
        return any(role.id == mod_role_id for role in member.roles)
    return False

async def ensure_setup(interaction: "discord.Interaction", db) -> bool:
    """Ensure guild has setup; if missing, notify user."""
    guild_config = await db.get_guild_config(interaction.guild.id)
    if not guild_config:
        await interaction.response.send_message(
            "❗ This server has no configuration. Please run `/setup` first to configure HWB-BirthdayHelper.",
            ephemeral=True
        )
        return False
    return True

# ---------------- Admin Cog ----------------
class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------------- Set Birthday for User ----------------
    @app_commands.command(name="setuserbirthday", description="Set a birthday for another user (Admin/Mod)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(user="User", day="Day", month="Month")
    async def setuserbirthday(self, interaction: "discord.Interaction", user: discord.Member, day: int, month: int):
        if user.bot:
            # Only show an ephemeral message; do not add to DB or pinned message
            await interaction.response.send_message(
                f"🤖 Nice try! I'm a bot, so I don't have a birthday… "
                f"but I *was created on {BOT_BIRTHDAY}th September*! 🎉\nThanks for caring! 😄",
                ephemeral=True
            )
            return
        if not await ensure_setup(interaction, self.bot.db):
            return

        guild_config = await self.bot.db.get_guild_config(interaction.guild.id)
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            logger.warning(f"Unauthorized access: {interaction.user.display_name} attempted setuserbirthday in {interaction.guild.name}")
            return

        await interaction.response.defer(ephemeral=True)
        result = parse_day_month_input(day, month)
        if not result:
            await interaction.followup.send("❗ Invalid day/month!", ephemeral=True)
            return

        day, month = result
        birthday_str = f"{month:02d}-{day:02d}"

        try:
            await self.bot.db.set_birthday(interaction.guild.id, user.id, birthday_str)
            # Update pinned birthday message
            all_birthdays = await self.bot.db.get_birthdays(interaction.guild.id)
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [uid for uid, bday in all_birthdays if is_birthday_on_date(bday, today)]
            pinned_msg = await update_pinned_birthday_message(interaction.guild, db=self.bot.db, highlight_today=birthdays_today)

            if pinned_msg and not pinned_msg.pinned:
                try:
                    await pinned_msg.pin()
                except discord.Forbidden:
                    logger.warning(f"Cannot pin birthday message in {interaction.guild.name}")

        except Exception as e:
            logger.error(f"Error setting birthday: {e}", exc_info=True)
            await interaction.followup.send("🚨 Failed to set user's birthday. Try again later.", ephemeral=True)
            return

        logger.info(f"👑 {interaction.user.display_name} set {user.display_name}'s birthday to {birthday_str} in {interaction.guild.name}")
        await interaction.followup.send(f"💌 {user.display_name}'s birthday is set to {format_birthday_display(birthday_str)}.", ephemeral=True)

    # ---------------- Delete Birthday for User ----------------
    @app_commands.command(name="deleteuserbirthday", description="Delete a user's birthday (Admin/Mod)")
    @app_commands.default_permissions(manage_guild=True)
    async def deleteuserbirthday(self, interaction: "discord.Interaction", user: discord.Member):
        if not await ensure_setup(interaction, self.bot.db):
            return

        guild_config = await self.bot.db.get_guild_config(interaction.guild.id)
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.db.delete_birthday(interaction.guild.id, user.id)
            all_birthdays = await self.bot.db.get_birthdays(interaction.guild.id)
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [uid for uid, bday in all_birthdays if is_birthday_on_date(bday, today)]
            await update_pinned_birthday_message(interaction.guild, db=self.bot.db, highlight_today=birthdays_today)

        except Exception as e:
            logger.error(f"Error deleting birthday: {e}", exc_info=True)
            await interaction.followup.send("🚨 Failed to delete user's birthday. Try again later.", ephemeral=True)
            return

        await interaction.followup.send(f"🗑️ {user.display_name}'s birthday has been deleted.", ephemeral=True)

    # ---------------- Import Birthdays ----------------
    @app_commands.command(name="importbirthdays", description="Import birthdays from a message (Admin/Mod)")
    @app_commands.default_permissions(manage_guild=True)
    async def importbirthdays(self, interaction: "discord.Interaction", channel: discord.TextChannel, message_id: str):
        if not await ensure_setup(interaction, self.bot.db):
            return

        guild_config = await self.bot.db.get_guild_config(interaction.guild.id)
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id")):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        updated_count = 0

        try:
            msg = await channel.fetch_message(int(message_id))
            lines = msg.content.splitlines()
            for line in lines:
                line = line.strip()
                if not line or "-" not in line:
                    continue

                try:
                    user_part, date_part = line.split("-", 1)
                    user_part, date_part = user_part.strip(), date_part.strip()
                except ValueError:
                    continue

                try:
                    if user_part.startswith("<@") and user_part.endswith(">"):
                        user_id = int(user_part.replace("<@", "").replace("!", "").replace(">", ""))
                    else:
                        user_id = int(user_part)
                except ValueError:
                    continue

                result = parse_day_month_input(*date_part.replace("/", " ").split())
                if not result:
                    continue
                day, month = result
                birthday_str = f"{month:02d}-{day:02d}"
                await self.bot.db.set_birthday(interaction.guild.id, user_id, birthday_str)
                updated_count += 1

            # Update pinned birthday message
            all_birthdays = await self.bot.db.get_birthdays(interaction.guild.id)
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [uid for uid, bday in all_birthdays if is_birthday_on_date(bday, today)]
            await update_pinned_birthday_message(interaction.guild, db=self.bot.db, highlight_today=birthdays_today)

            await interaction.followup.send(f"✅ Imported {updated_count} birthdays.", ephemeral=True)

        except discord.NotFound:
            await interaction.followup.send("🔍 Message not found or inaccessible.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error importing birthdays: {e}", exc_info=True)
            await interaction.followup.send("🚨 Error importing birthdays. Try again later.", ephemeral=True)

    # ---------------- Clear All Birthdays with Confirmation ----------------
    @app_commands.command(
        name="clearallbirthdays",
        description="Remove all birthdays and reset the bot's configuration for this server (Admin only)"
    )
    @app_commands.default_permissions(administrator=True)  # ✅ Admins only
    async def clearallbirthdays(self, interaction: "discord.Interaction"):
        if not await ensure_setup(interaction, self.bot.db):
            return

        # ✅ Double-check admin permission
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❗ Only **server admins** can use this command.", ephemeral=True)
            return

        class ClearConfirmView(View):
            def __init__(self, bot, guild_id, author_id):
                super().__init__(timeout=60)
                self.bot = bot
                self.guild_id = guild_id
                self.author_id = author_id

            @discord.ui.button(label="✅ Yes, Clear All", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction_button: "discord.Interaction", button: Button):
                if interaction_button.user.id != self.author_id:
                    await interaction_button.response.send_message("❌ You cannot confirm this action.", ephemeral=True)
                    return

                await interaction_button.response.edit_message(
                    content="🧹 Clearing all birthdays and resetting configuration...", view=None
                )
                try:
                    await self.bot.db.db.execute("DELETE FROM birthdays WHERE guild_id = ?", (self.guild_id,))
                    await self.bot.db.db.execute("DELETE FROM guild_config WHERE guild_id = ?", (self.guild_id,))
                    await self.bot.db.db.execute("DELETE FROM wished_today WHERE guild_id = ?", (self.guild_id,))
                    await self.bot.db.db.commit()

                    logger.info(f"🧹 {interaction_button.user.display_name} cleared all birthdays/config in {interaction_button.guild.name}")
                    await interaction_button.followup.send(
                        "✅ All birthdays and configuration have been cleared.\n"
                        "You can now run `/setup` again to reconfigure the bot.",
                        ephemeral=True
                    )
                except Exception as e:
                    logger.error(f"Error clearing birthdays/config: {e}", exc_info=True)
                    await interaction_button.followup.send("🚨 Failed to clear birthdays/config.", ephemeral=True)
                self.stop()

            @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction_button: "discord.Interaction", button: Button):
                if interaction_button.user.id != self.author_id:
                    await interaction_button.response.send_message("❌ You cannot cancel this action.", ephemeral=True)
                    return
                await interaction_button.response.edit_message(content="❌ Clearing cancelled.", view=None)
                self.stop()

        view = ClearConfirmView(self.bot, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            "⚠️ **Are you sure you want to clear all birthdays and reset the bot?**\n"
            "This will delete all birthdays and settings, and cannot be undone!",
            view=view,
            ephemeral=True
        )


# ---------------- Setup ----------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
