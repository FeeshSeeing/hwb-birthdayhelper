import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils import parse_day_month_input, format_birthday_display, update_pinned_birthday_message, is_birthday_on_date
from logger import logger
import datetime as dt

CONFETTI_ICON = "🎉 "
ENTRIES_PER_PAGE = 20
BOT_BIRTHDAY = 9  # September 9th, for fun message

# ----------------- Setup Check -----------------
async def ensure_setup(interaction: discord.Interaction) -> bool:
    guild_config = await interaction.client.db.get_guild_config(interaction.guild.id)
    if not guild_config:
        await interaction.response.send_message(
            "❗ Please run `/setup` first to configure HWB-BirthdayHelper for this server!",
            ephemeral=True
        )
        return False
    return True

# ---------------- Birthday Commands ----------------
class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.refresh_pinned_messages.start()

    # ---------------- Daily Refresh ----------------
    @tasks.loop(hours=24)
    async def refresh_pinned_messages(self):
        for guild in self.bot.guilds:
            try:
                birthdays = await self.bot.db.get_birthdays(guild.id)
                today = dt.datetime.now(dt.timezone.utc)
                birthdays_today = [
                    uid for uid, bday in birthdays 
                    if is_birthday_on_date(bday, today)
                    and (member := guild.get_member(uid)) and not member.bot
                ]
                await update_pinned_birthday_message(
                    guild,
                    db=self.bot.db,
                    highlight_today=birthdays_today
                )
            except Exception as e:
                logger.error(f"Failed daily pinned refresh in {guild.name}: {e}")

    @refresh_pinned_messages.before_loop
    async def before_refresh(self):
        await self.bot.wait_until_ready()

    # ---------------- Commands ----------------
    @app_commands.command(name="setbirthday", description="Set your birthday (day then month)")
    @app_commands.describe(day="Day of birthday", month="Month of birthday")
    async def setbirthday(self, interaction: discord.Interaction, day: int, month: int):
        if not await ensure_setup(interaction):
            return

        # Prevent bot from being set
        if interaction.user.bot:
            await interaction.response.send_message(
                f"🤖 Nice try! I’m a bot, so I don’t have a birthday… "
                f"but I *was created on {BOT_BIRTHDAY}th September*! 🎉\nThanks for caring! 😄",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        result = parse_day_month_input(day, month)
        if not result:
            await interaction.followup.send("❗ Invalid day/month! Example: 25 12", ephemeral=True)
            return

        day, month = result
        birthday_str = f"{month:02d}-{day:02d}"

        try:
            await self.bot.db.set_birthday(interaction.guild.id, interaction.user.id, birthday_str)
            all_birthdays = await self.bot.db.get_birthdays(interaction.guild.id)
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [
                uid for uid, bday in all_birthdays 
                if is_birthday_on_date(bday, today)
                and (member := interaction.guild.get_member(uid)) and not member.bot
            ]
            await update_pinned_birthday_message(
                interaction.guild,
                db=self.bot.db,
                highlight_today=birthdays_today
            )
        except Exception as e:
            logger.error(f"Error setting birthday for {interaction.user.display_name}: {e}")
            await interaction.followup.send("🚨 Failed to set birthday. Try again later.", ephemeral=True)
            return

        human_readable = format_birthday_display(birthday_str)
        await interaction.followup.send(
            f"All done 💌 Your special day is marked as {human_readable}. Hugs are on the way!", ephemeral=True
        )

    @app_commands.command(name="deletebirthday", description="Delete your birthday")
    async def deletebirthday(self, interaction: discord.Interaction):
        if not await ensure_setup(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        try:
            await self.bot.db.delete_birthday(interaction.guild.id, interaction.user.id)
            all_birthdays = await self.bot.db.get_birthdays(interaction.guild.id)
            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [
                uid for uid, bday in all_birthdays 
                if is_birthday_on_date(bday, today)
                and (member := interaction.guild.get_member(uid)) and not member.bot
            ]
            await update_pinned_birthday_message(
                interaction.guild,
                db=self.bot.db,
                highlight_today=birthdays_today
            )
        except Exception as e:
            logger.error(f"Error deleting birthday for {interaction.user.display_name}: {e}")
            await interaction.followup.send("🚨 Failed to delete birthday. Try again later.", ephemeral=True)
            return

        await interaction.followup.send("All done 🎈 Your birthday has been deleted.", ephemeral=True)

    @app_commands.command(name="viewbirthdays", description="View upcoming birthdays (first 20)")
    async def viewbirthdays(self, interaction: discord.Interaction):
        if not await ensure_setup(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        try:
            birthdays = await self.bot.db.get_birthdays(interaction.guild.id)
            if not birthdays:
                await interaction.followup.send("📂 No birthdays found yet.", ephemeral=True)
                return

            today = dt.datetime.now(dt.timezone.utc)
            birthdays_today = [
                uid for uid, bday in birthdays 
                if is_birthday_on_date(bday, today)
                and (member := interaction.guild.get_member(uid)) and not member.bot
            ]
            await update_pinned_birthday_message(
                interaction.guild,
                db=self.bot.db,
                highlight_today=birthdays_today,
                manual=True
            )

            # Sort upcoming birthdays
            def upcoming_sort_key(b):
                month, day = map(int, b[1].split("-"))
                try:
                    current = dt.datetime(today.year, month, day, tzinfo=dt.timezone.utc)
                except ValueError:
                    if month == 2 and day == 29:
                        current = dt.datetime(today.year, 2, 28, tzinfo=dt.timezone.utc)
                    else:
                        logger.warning(f"Invalid birthday {b[1]} for user {b[0]}")
                        return float("inf")
                if current < today and not is_birthday_on_date(b[1], today):
                    try:
                        current = dt.datetime(today.year + 1, month, day, tzinfo=dt.timezone.utc)
                    except ValueError:
                        if month == 2 and day == 29:
                            current = dt.datetime(today.year + 1, 2, 28, tzinfo=dt.timezone.utc)
                        else:
                            return float("inf")
                return (current - today).total_seconds()

            birthdays_sorted = sorted(birthdays, key=upcoming_sort_key)
            first_page = birthdays_sorted[:ENTRIES_PER_PAGE]

            guild_config = await self.bot.db.get_guild_config(interaction.guild.id)
            check_hour = guild_config.get("check_hour", 7)

            lines = []
            for uid, bday in first_page:
                try:
                    member = interaction.guild.get_member(uid) or await interaction.guild.fetch_member(uid)
                    if member.bot:
                        continue  # Skip bot
                    display_name = member.display_name
                except discord.NotFound:
                    display_name = f"User {uid}"
                prefix = "・"
                if is_birthday_on_date(bday, today):
                    prefix += CONFETTI_ICON
                prefix += " "
                lines.append(f"{prefix}{display_name} - {format_birthday_display(bday)}")

            content = "🎂 BIRTHDAY LIST 🎂\n------------------------\n"
            content += "\n".join(lines)
            content += "\n\n"
            content += "-# 💡 Tip: Use /setbirthday to add your own special day!\n"
            content += f"-# ⏰ Bot checks birthdays daily at {check_hour}:00 UTC"

            await interaction.followup.send(content=content, ephemeral=True)
        except Exception as e:
            logger.error(f"Error viewing birthdays: {e}")
            await interaction.followup.send("🚨 Failed to view birthday list. Try again later.", ephemeral=True)

# ---------------- Setup Cog ----------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
