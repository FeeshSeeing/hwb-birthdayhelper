import discord
from discord.ext import commands, tasks
import datetime
import os
from dotenv import load_dotenv
import database

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.default()
intents.members = True
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"{bot.user} has connected!")
    await database.init_db()
    birthday_check.start()

# Command to set birthday
@bot.command(name="setbirthday")
async def set_birthday(ctx, date: str):
    """Set your birthday in MM-DD format"""
    try:
        datetime.datetime.strptime(date, "%m-%d")
        await database.set_birthday(str(ctx.author.id), date)
        await ctx.send(f"Birthday set to {date} 🎉")
    except ValueError:
        await ctx.send("Invalid format! Use MM-DD.")

# Birthday check task
@tasks.loop(hours=24)
async def birthday_check():
    today = datetime.datetime.now().strftime("%m-%d")
    birthdays = await database.get_birthdays()
    guild = bot.get_guild(GUILD_ID)
    for user_id, birthday in birthdays:
        if birthday == today:
            member = guild.get_member(int(user_id))
            if member:
                channel = guild.get_channel(1331065109354778755)
                # channel = guild.text_channels[0]  # You can customize the channel
                await channel.send(f"Happy Birthday {member.mention}! 🎂🎉")



# Run bot
client.run(TOKEN)
