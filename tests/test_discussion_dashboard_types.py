import unittest

from velvet_bot.handlers.analytics_discussion_overrides import (
    _get_discussion_dashboard,
)


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def __init__(self):
        self.query = ""
        self.args = ()

    async def fetchrow(self, query, *args):
        self.query = query
        self.args = args
        return {
            "title": "Velvet discussion",
            "total_messages": 12,
            "unique_participants": 4,
            "reply_messages": 7,
            "media_messages": 2,
            "spoiler_messages": 1,
            "prompt_messages": 0,
            "total_reactions": 15,
            "first_message_at": None,
            "last_message_at": None,
        }


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


class _Database:
    def __init__(self, connection):
        self.pool = _Pool(connection)

    def _require_pool(self):
        return self.pool


class DiscussionDashboardTypeTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_id_is_bound_as_bigint(self):
        connection = _Connection()
        database = _Database(connection)

        result = await _get_discussion_dashboard(
            database,
            -1003859952761,
            period="all",
        )

        self.assertIn("WHERE t.chat_id = $1::BIGINT", connection.query)
        self.assertIn("t.chat_id::TEXT", connection.query)
        self.assertEqual(-1003859952761, connection.args[0])
        self.assertEqual(12, result.total_messages)
        self.assertEqual("Velvet discussion", result.title)


if __name__ == "__main__":
    unittest.main()
