from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from velvet_bot.alias_management import (
    get_character_alias_by_id,
    get_character_alias_summary,
)
from velvet_bot.character_aliases import CharacterAlias


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


class AliasManagementBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_queries_use_public_database_boundary(self) -> None:
        source = inspect.getsource(__import__("velvet_bot.alias_management", fromlist=["*"]))
        self.assertNotIn("._require_pool()", source)
        self.assertEqual(2, source.count("database.acquire()"))

    async def test_alias_lookup_maps_row_to_domain_model(self) -> None:
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "id": "17",
                    "character_id": "41",
                    "character_name": "Каэль",
                    "alias": "Кей",
                    "normalized_alias": "кей",
                    "source": "manual",
                }
            )
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await get_character_alias_by_id(database, alias_id=17)

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, alias_id = connection.fetchrow.await_args.args
        self.assertIn("FROM character_aliases AS a", sql)
        self.assertIn("WHERE a.id = $1", sql)
        self.assertEqual(alias_id, 17)
        self.assertEqual(
            result,
            CharacterAlias(
                id=17,
                character_id=41,
                character_name="Каэль",
                alias="Кей",
                normalized_alias="кей",
                source="manual",
            ),
        )

    async def test_missing_alias_returns_none(self) -> None:
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=None))
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await get_character_alias_by_id(database, alias_id=404)

        self.assertIsNone(result)

    async def test_summary_loads_name_before_alias_list(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value="Каэль"))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))
        aliases = [
            CharacterAlias(
                id=17,
                character_id=41,
                character_name="Каэль",
                alias="Кей",
                normalized_alias="кей",
                source="manual",
            )
        ]

        with patch(
            "velvet_bot.alias_management.list_character_aliases",
            new=AsyncMock(return_value=aliases),
        ) as list_aliases:
            result = await get_character_alias_summary(database, character_id=41)

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, character_id = connection.fetchval.await_args.args
        self.assertEqual(sql, "SELECT name FROM characters WHERE id = $1")
        self.assertEqual(character_id, 41)
        list_aliases.assert_awaited_once_with(database, character_id=41)
        self.assertEqual(result, ("Каэль", aliases))

    async def test_missing_character_skips_alias_query(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=None))
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        with patch(
            "velvet_bot.alias_management.list_character_aliases",
            new=AsyncMock(),
        ) as list_aliases:
            result = await get_character_alias_summary(database, character_id=404)

        list_aliases.assert_not_awaited()
        self.assertEqual(result, (None, []))


if __name__ == "__main__":
    unittest.main()
