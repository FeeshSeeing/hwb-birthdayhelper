# cogs/debug_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from cogs.admin import is_admin_or_mod
from logger import logger

class DebugCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="showwished", description="Show users who have already been wished today.")
    @app_commands.default_permissions(manage_guild=True)
    async def show_wished(self, interaction: discord.Interaction):
        """Display the wished_today table for this guild."""
        guild_config = await self.bot.db.get_guild_config(interaction.guild.id)
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id") if guild_config else None):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        db_conn = self.bot.db.db  # Persistent connection
        try:
            async with db_conn.execute(
                "SELECT user_id, date FROM wished_today WHERE guild_id = ?", (interaction.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()

            if not rows:
                await interaction.followup.send("✅ No one has been wished today in this server.")
                return

            message = "\n".join([f"<@{row['user_id']}> — {row['date']}" for row in rows])
            await interaction.followup.send(
                f"📋 **Already Wished Today:**\n{message}", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error fetching wished_today for guild {interaction.guild.name}: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error reading database: {e}", ephemeral=True)

    @app_commands.command(name="clearwished", description="Clear today's wished users (FOR TESTING).")
    @app_commands.default_permissions(manage_guild=True)
    async def clear_wished(self, interaction: discord.Interaction):
        """Clear the wished_today table for this guild."""
        guild_config = await self.bot.db.get_guild_config(interaction.guild.id)
        if not is_admin_or_mod(interaction.user, guild_config.get("mod_role_id") if guild_config else None):
            await interaction.response.send_message("❗ You are not allowed to use this.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        db_conn = self.bot.db.db  # Persistent connection
        try:
            await db_conn.execute(
                "DELETE FROM wished_today WHERE guild_id = ?", (interaction.guild.id,)
            )
            await db_conn.commit()
            await interaction.followup.send("🗑️ Cleared wished users for this guild.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error clearing wished_today for guild {interaction.guild.name}: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error clearing wished users: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(DebugCog(bot))
