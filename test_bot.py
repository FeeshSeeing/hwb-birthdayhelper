# test_bot.py
import sys
import os

# Add the project root to sys.path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

import unittest
import unittest.mock
import asyncio
import datetime as dt
import discord  # Essential to import discord itself

# --- Async context manager mocks for aiosqlite ---
class AsyncCursorMock:
    def __init__(self, fetchall_return=None):
        self.fetchall_return = fetchall_return or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def fetchall(self):
        return self.fetchall_return

class AsyncConnectionMock:
    def __init__(self, cursor_return=None):
        self.cursor_return = cursor_return or AsyncCursorMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    def execute(self, *args, **kwargs):
        return self.cursor_return

    async def commit(self):
        pass

# --- Mock Discord for testing cogs ---
class MockMember:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name
        self.roles = []
        self.guild_permissions = unittest.mock.Mock()
        self.guild_permissions.administrator = False

class MockGuild:
    def __init__(self, id, name="Test Guild"):
        self.id = id
        self.name = name
        self._members = {}
        self._channels = {}
        self.me = MockMember(12345, "Bot User")
        self.add_member(self.me)

    def get_member(self, user_id):
        return self._members.get(user_id)

    def add_member(self, member: MockMember):
        self._members[member.id] = member

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)

    def add_channel(self, channel: unittest.mock.Mock):
        self._channels[channel.id] = channel

class MockTextChannel:
    def __init__(self, id, name="test-channel"):
        self.id = id
        self.name = name
        self._messages = []
        self._permissions_for_bot = unittest.mock.Mock()
        self._permissions_for_bot.send_messages = True
        self._permissions_for_bot.manage_messages = True
        self.permissions_for = unittest.mock.Mock(return_value=self._permissions_for_bot)

    async def fetch_message(self, message_id):
        for msg in self._messages:
            if str(msg.id) == str(message_id):
                return msg
        raise discord.NotFound("Message not found")

    async def send(self, content, view=None):
        msg = MockMessage(len(self._messages) + 1, content)
        self._messages.append(msg)
        return msg

    async def pin(self):
        pass

class MockMessage:
    def __init__(self, id, content):
        self.id = id
        self.content = content

    async def edit(self, content=None, view=None):
        if content:
            self.content = content

    async def original_response(self):
        return self

    async def pin(self):
        pass

class MockInteraction:
    def __init__(self, user_id, guild_id, channel_id):
        self.user = MockMember(user_id, f"User{user_id}")
        self.guild = MockGuild(guild_id)
        self.channel = MockTextChannel(channel_id)
        self.guild.add_member(self.user)
        self.guild.add_channel(self.channel)
        self.response = unittest.mock.Mock()
        self.response.defer = unittest.mock.AsyncMock()
        self.response.send_message = unittest.mock.AsyncMock()
        self.response.edit_message = unittest.mock.AsyncMock()
        self.followup = unittest.mock.Mock()
        self.followup.send = unittest.mock.AsyncMock()

# --- Mock discord.py exceptions ---
unittest.mock.discord = unittest.mock.Mock()
unittest.mock.discord.NotFound = discord.NotFound
unittest.mock.discord.Forbidden = discord.Forbidden
unittest.mock.discord.HTTPException = discord.HTTPException

# --- Import actual modules to test ---
import config
config.DB_FILE = "test_birthdays.db"

import database
import utils
from cogs.admin import is_admin_or_mod
from cogs.birthdays import Birthdays
from cogs.setup_cog import SetupCog
from cogs.admin import Admin
from cogs.testdate import TestDateCog

# --- Utility for running async tests ---
def async_test(coro):
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop_policy().new_event_loop()
        try:
            return loop.run_until_complete(coro(*args, **kwargs))
        finally:
            loop.close()
    return wrapper

# --- Database Tests ---
class TestDatabase(unittest.TestCase):
    def setUp(self):
        if os.path.exists(config.DB_FILE):
            os.remove(config.DB_FILE)
        asyncio.run(database.init_db())

    def tearDown(self):
        if os.path.exists(config.DB_FILE):
            os.remove(config.DB_FILE)

    @async_test
    async def test_set_and_get_birthday(self):
        guild_id = "12345"
        user_id = "67890"
        birthday = "05-15"
        await database.set_birthday(guild_id, user_id, birthday)
        birthdays = await database.get_birthdays(guild_id)
        self.assertIn((user_id, birthday), birthdays)

# --- Utils Tests ---
class TestUtils(unittest.TestCase):
    @unittest.mock.patch('utils.logger')
    @unittest.mock.patch('database.get_birthdays', new_callable=unittest.mock.AsyncMock)
    @unittest.mock.patch('database.get_guild_config', new_callable=unittest.mock.AsyncMock)
    @unittest.mock.patch('utils.aiosqlite.connect', new_callable=unittest.mock.AsyncMock)
    @async_test
    async def test_update_pinned_birthday_message_no_config(self, mock_connect, mock_get_guild_config, mock_get_birthdays, mock_logger):
        mock_guild = MockGuild(123)
        mock_get_guild_config.return_value = None  # No config set

        await utils.update_pinned_birthday_message(mock_guild)

        # Ensure DB queried and warning logged
        self.assertTrue(mock_connect.called)
        mock_logger.warning.assert_called_with(unittest.mock.ANY)

    @unittest.mock.patch('utils.logger')
    @unittest.mock.patch('database.get_birthdays', new_callable=unittest.mock.AsyncMock)
    @unittest.mock.patch('database.get_guild_config', new_callable=unittest.mock.AsyncMock)
    @unittest.mock.patch('utils.aiosqlite.connect', new_callable=unittest.mock.AsyncMock)
    @async_test
    async def test_update_pinned_birthday_message_no_channel(self, mock_connect, mock_get_guild_config, mock_get_birthdays, mock_logger):
        mock_guild = MockGuild(123)
        mock_get_guild_config.return_value = {"channel_id": "999", "check_hour": 9}  # Minimal config
        mock_get_birthdays.return_value = []

        # Force get_channel to return None
        mock_guild.get_channel = unittest.mock.Mock(return_value=None)

        await utils.update_pinned_birthday_message(mock_guild)

        # Ensure DB queried and warning logged
        self.assertTrue(mock_connect.called)
        mock_logger.warning.assert_called_with(unittest.mock.ANY)

# --- Other test classes (Admin, BirthdayCog, SetupCog) remain unchanged ---
# Keep your existing test code for those

if __name__ == "__main__":
    unittest.main()
