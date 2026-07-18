from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import velvet_bot.character_aliases as aliases_module
from velvet_bot.character_aliases import (
    CharacterAlias,
    add_character_alias,
    delete_character_alias,
    ensure_name_aliases,
    list_character_aliases,
    rebuild_hashtag_character_links,
)


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


class CharacterAliasesBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_module_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(aliases_module)
        self.assertNotIn("._require_pool()", source)
        self.assertEqual(5, source.count("database.acquire()"))

    async def test_ensure_name_aliases_preserves_insert_count(self) -> None:
        connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {"id": "1", "name": "Каэль Лэнг"},
                    {"id": "2", "name": "---"},
                ]
            ),
            execute=AsyncMock(return_value="INSERT 0 1"),
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await ensure_name_aliases(database)

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        connection.fetch.assert_awaited_once_with(
            "SELECT id, name FROM characters ORDER BY id"
        )
        self.assertEqual(connection.execute.await_count, 1)
        sql, character_id, alias, normalized = connection.execute.await_args.args
        self.assertIn("ON CONFLICT (normalized_alias) DO NOTHING", sql)
        self.assertEqual((character_id, alias, normalized), (1, "Каэль Лэнг", "каэльлэнг"))
        self.assertEqual(result, 1)

    async def test_list_aliases_maps_rows(self) -> None:
        connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {
                        "id": "17",
                        "character_id": "41",
                        "character_name": "Каэль",
                        "alias": "Кей",
                        "normalized_alias": "кей",
                        "source": "manual",
                    }
                ]
            )
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await list_character_aliases(database, character_id=41)

        sql, character_id = connection.fetch.await_args.args
        self.assertIn("WHERE a.character_id = $1", sql)
        self.assertIn("ORDER BY CASE a.source", sql)
        self.assertEqual(character_id, 41)
        self.assertEqual(
            result,
            [
                CharacterAlias(
                    id=17,
                    character_id=41,
                    character_name="Каэль",
                    alias="Кей",
                    normalized_alias="кей",
                    source="manual",
                )
            ],
        )

    async def test_add_alias_preserves_validation_persistence_and_hashtag_link(self) -> None:
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                side_effect=[
                    {"id": 41, "name": "Каэль"},
                    None,
                    {
                        "id": "17",
                        "character_id": "41",
                        "alias": "Кей Лэнг",
                        "normalized_alias": "кейлэнг",
                        "source": "manual",
                    },
                ]
            ),
            execute=AsyncMock(return_value="UPDATE 2"),
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await add_character_alias(
            database,
            character_id=41,
            alias="  Кей   Лэнг  ",
            created_by=7221553045,
        )

        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        self.assertEqual(connection.fetchrow.await_count, 3)
        character_query = connection.fetchrow.await_args_list[0].args
        self.assertEqual(
            character_query,
            ("SELECT id, name FROM characters WHERE id = $1", 41),
        )
        conflict_sql, conflict_normalized = connection.fetchrow.await_args_list[1].args
        self.assertIn("WHERE a.normalized_alias = $1", conflict_sql)
        self.assertEqual(conflict_normalized, "кейлэнг")
        insert_args = connection.fetchrow.await_args_list[2].args
        self.assertIn("ON CONFLICT (character_id, normalized_alias) DO UPDATE", insert_args[0])
        self.assertEqual(insert_args[1:], (41, "Кей Лэнг", "кейлэнг", 7221553045))
        update_sql, update_character_id, update_normalized = connection.execute.await_args.args
        self.assertIn("UPDATE channel_post_hashtags", update_sql)
        self.assertEqual((update_character_id, update_normalized), (41, "кейлэнг"))
        self.assertEqual(
            result,
            CharacterAlias(
                id=17,
                character_id=41,
                character_name="Каэль",
                alias="Кей Лэнг",
                normalized_alias="кейлэнг",
                source="manual",
            ),
        )

    async def test_delete_alias_preserves_guard_and_unlink(self) -> None:
        connection = SimpleNamespace(
            fetchrow=AsyncMock(return_value={"id": 17}),
            execute=AsyncMock(return_value="UPDATE 1"),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await delete_character_alias(
            database,
            character_id=41,
            alias="Кей-Лэнг",
        )

        delete_sql, character_id, normalized = connection.fetchrow.await_args.args
        self.assertIn("AND source <> 'name'", delete_sql)
        self.assertEqual((character_id, normalized), (41, "кейлэнг"))
        unlink_sql, unlink_character_id, unlink_normalized = connection.execute.await_args.args
        self.assertIn("AND NOT EXISTS", unlink_sql)
        self.assertEqual((unlink_character_id, unlink_normalized), (41, "кейлэнг"))
        self.assertTrue(result)

    async def test_empty_delete_skips_database(self) -> None:
        database = SimpleNamespace(acquire=Mock())

        result = await delete_character_alias(database, character_id=41, alias="---")

        database.acquire.assert_not_called()
        self.assertFalse(result)

    async def test_rebuild_preserves_transaction_and_counts(self) -> None:
        transaction = _AsyncContext(None)
        connection = SimpleNamespace(
            transaction=Mock(return_value=transaction),
            execute=AsyncMock(
                side_effect=["UPDATE 5", "UPDATE 2", "UPDATE 1"]
            ),
            fetch=AsyncMock(
                return_value=[
                    {"normalized_alias": "каэль", "character_id": "41"},
                    {"normalized_alias": "эрик", "character_id": "42"},
                ]
            ),
            fetchval=AsyncMock(return_value="10"),
        )
        connection_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=connection_context))

        result = await rebuild_hashtag_character_links(database)

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(connection_context.entered)
        self.assertTrue(connection_context.exited)
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        self.assertEqual(connection.execute.await_count, 3)
        self.assertEqual(
            connection.execute.await_args_list[1].args[1:],
            (41, "каэль"),
        )
        self.assertEqual(
            connection.execute.await_args_list[2].args[1:],
            (42, "эрик"),
        )
        connection.fetchval.assert_awaited_once_with(
            "SELECT COUNT(*) FROM channel_post_hashtags"
        )
        self.assertEqual(result, (3, 10))


if __name__ == "__main__":
    unittest.main()
