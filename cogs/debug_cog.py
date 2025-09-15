# cogs/debug_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from config import DB_FILE

class DebugCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="showwished", description="Show users who have already been wished today.")
    async def show_wished(self, interaction: discord.Interaction):
        """Display the wished_today table for this guild."""
        await interaction.response.defer(thinking=True, ephemeral=True)

        guild_id = str(interaction.guild.id)
        async with aiosqlite.connect(DB_FILE) as db:
            try:
                async with db.execute(
                    "SELECT user_id, wished_date FROM wished_today WHERE guild_id = ?", (guild_id,)
                ) as cursor:
                    rows = await cursor.fetchall()

                if not rows:
                    await interaction.followup.send("✅ No one has been wished today in this server.")
                    return

                message = "\n".join(
                    [f"<@{user_id}> — {wished_date}" for user_id, wished_date in rows]
                )
                await interaction.followup.send(
                    f"📋 **Already Wished Today:**\n{message}", ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(f"❌ Error reading database: {e}", ephemeral=True)

    @app_commands.command(name="clearwished", description="Clear today's wished users (FOR TESTING).")
    @app_commands.checks.has_permissions(administrator=True)
    async def clear_wished(self, interaction: discord.Interaction):
        """Clear the wished_today table for this guild."""
        await interaction.response.defer(thinking=True, ephemeral=True)

        guild_id = str(interaction.guild.id)
        async with aiosqlite.connect(DB_FILE) as db:
            try:
                await db.execute("DELETE FROM wished_today WHERE guild_id = ?", (guild_id,))
                await db.commit()
                await interaction.followup.send("🗑️ Cleared wished users for this guild.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Error clearing wished users: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(DebugCog(bot))
