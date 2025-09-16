import asyncio
from bot import bot
from tasks import run_birthday_check_once

GUILD_ID = 1415476237618647154  # replace with the guild you want to test

async def test_birthday():
    await bot.wait_until_ready()
    
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f"❌ Guild {GUILD_ID} not found!")
        return

    print(f"✅ Found guild: {guild.name}")

    # Run birthday check once for this guild
    await run_birthday_check_once(bot, guild=guild)

    print("🎉 Birthday check executed!")

asyncio.run(test_birthday())
