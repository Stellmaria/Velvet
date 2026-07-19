import unittest

from velvet_bot.analytics_dashboard import get_discussion_dashboard


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


class _Database:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


class DiscussionDashboardTypeTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_id_is_bound_through_public_dashboard_query(self):
        connection = _Connection()
        database = _Database(connection)

        result = await get_discussion_dashboard(
            database,
            -1003859952761,
            period="all",
        )

        self.assertIn("WHERE t.chat_id = $1", connection.query)
        self.assertIn("COALESCE(MAX(t.title), $1::TEXT)", connection.query)
        self.assertEqual(-1003859952761, connection.args[0])
        self.assertEqual(12, result.total_messages)
        self.assertEqual("Velvet discussion", result.title)


if __name__ == "__main__":
    unittest.main()
