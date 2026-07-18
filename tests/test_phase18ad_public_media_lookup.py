from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.public_media_lookup import get_character_media_offset


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


class PublicMediaLookupBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_query_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(get_character_media_offset)
        self.assertNotIn("._require_pool()", source)
        self.assertEqual(1, source.count("database.acquire()"))
        self.assertIn("ROW_NUMBER() OVER", source)
        self.assertIn("ORDER BY created_at DESC, media_id DESC", source)

    async def test_offset_query_preserves_filters_and_integer_mapping(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=3))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await get_character_media_offset(
            database,
            character_id=41,
            media_id=99,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, character_id, media_id = connection.fetchval.await_args.args
        self.assertIn("WHERE character_id = $1", sql)
        self.assertIn("WHERE media_id = $2", sql)
        self.assertEqual((character_id, media_id), (41, 99))
        self.assertEqual(result, 3)

    async def test_missing_media_returns_none(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=None))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await get_character_media_offset(
            database,
            character_id=41,
            media_id=404,
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
