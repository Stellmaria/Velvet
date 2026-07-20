from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import velvet_bot.media_set_actions as actions
import velvet_bot.media_set_actions_repository as repository_module
from velvet_bot.media_set_actions_repository import (
    CreatedMediaSetRecord,
    MediaSetActionsRepository,
)
from velvet_bot.media_sets import CreatedMediaSet


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


class _TransactionContext:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


class MediaSetActionsRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def test_layer_boundary_is_explicit(self) -> None:
        service_source = inspect.getsource(actions)
        repository_source = inspect.getsource(repository_module)
        self.assertNotIn("._require_pool()", service_source)
        self.assertNotIn("database.acquire()", service_source)
        self.assertNotIn("._require_pool()", repository_source)
        self.assertEqual(1, repository_source.count("self._database.acquire()"))
        self.assertIn("MediaSetActionsRepository", service_source)

    async def test_repository_preserves_transaction_and_prompt_propagation(self) -> None:
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=51),
            execute=AsyncMock(return_value="UPDATE 3"),
            transaction=Mock(return_value=transaction),
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await MediaSetActionsRepository(database).set_prompt_post_url(
            media_set_id=51,
            prompt_post_url="https://t.me/channel/123",
        )

        self.assertTrue(result)
        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        set_sql, set_id, prompt_url = connection.fetchval.await_args.args
        self.assertIn("UPDATE media_sets", set_sql)
        self.assertIn("RETURNING id", set_sql)
        self.assertEqual((set_id, prompt_url), (51, "https://t.me/channel/123"))
        propagation_sql, propagation_id, propagation_url = connection.execute.await_args.args
        self.assertIn("UPDATE character_media AS cm", propagation_sql)
        self.assertIn("FROM media_files AS mf", propagation_sql)
        self.assertIn("cm.prompt_post_url IS DISTINCT FROM", propagation_sql)
        self.assertEqual(
            (propagation_id, propagation_url),
            (51, "https://t.me/channel/123"),
        )

    async def test_repository_missing_set_short_circuits_child_update(self) -> None:
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=None),
            execute=AsyncMock(),
            transaction=Mock(return_value=transaction),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await MediaSetActionsRepository(database).set_prompt_post_url(
            media_set_id=404,
            prompt_post_url="https://t.me/channel/123",
        )

        self.assertFalse(result)
        connection.execute.assert_not_awaited()
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)

    async def test_create_repository_cleans_overlapping_pending_candidates(self) -> None:
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "id": 7,
                    "suggested_title": "KR · сет",
                    "prompt_post_url": None,
                    "status": "pending",
                }
            ),
            fetch=AsyncMock(return_value=[{"media_id": 11}, {"media_id": 12}]),
            fetchval=AsyncMock(return_value=51),
            execute=AsyncMock(return_value="OK"),
            transaction=Mock(return_value=transaction),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await MediaSetActionsRepository(database).create_media_set(
            candidate_id=7,
            created_by=42,
        )

        self.assertEqual(result.media_ids, (11, 12))
        self.assertEqual(result.id, 51)
        sqls = [call.args[0] for call in connection.execute.await_args_list]
        self.assertIn("UPDATE media_files", sqls[0])
        self.assertIn("status = 'accepted'", sqls[1])
        self.assertIn("DELETE FROM media_set_candidate_items", sqls[2])
        self.assertIn("COUNT(*)", sqls[3])
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)


class MediaSetActionsServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_prompt_url_normalization_and_validation_are_preserved(self) -> None:
        self.assertEqual(
            actions.normalize_prompt_post_url("  https://t.me/channel_name/123  "),
            "https://t.me/channel_name/123",
        )
        for value in (
            "http://t.me/channel/123",
            "https://t.me/channel",
            "https://example.com/channel/123",
            "https://t.me/channel/not-a-number",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "ссылка на пост Telegram"):
                    actions.normalize_prompt_post_url(value)

    async def test_set_prompt_delegates_normalized_values_and_maps_missing_set(self) -> None:
        repository = SimpleNamespace(
            set_prompt_post_url=AsyncMock(side_effect=[True, False])
        )
        database = SimpleNamespace()
        repository_factory = Mock(return_value=repository)

        with patch.object(
            actions,
            "MediaSetActionsRepository",
            new=repository_factory,
        ):
            result = await actions.set_media_set_prompt(
                database,
                media_set_id="51",
                prompt_post_url="  https://t.me/channel/123  ",
            )
            with self.assertRaisesRegex(ValueError, "Сет больше не найден"):
                await actions.set_media_set_prompt(
                    database,
                    media_set_id="404",
                    prompt_post_url="https://t.me/channel/404",
                )

        self.assertEqual(result, "https://t.me/channel/123")
        self.assertEqual(repository_factory.call_count, 2)
        self.assertEqual(
            repository.set_prompt_post_url.await_args_list[0].kwargs,
            {
                "media_set_id": 51,
                "prompt_post_url": "https://t.me/channel/123",
            },
        )
        self.assertEqual(
            repository.set_prompt_post_url.await_args_list[1].kwargs,
            {
                "media_set_id": 404,
                "prompt_post_url": "https://t.me/channel/404",
            },
        )

    async def test_create_wrapper_maps_repository_record(self) -> None:
        record = CreatedMediaSetRecord(
            id=51,
            title="KR · сет",
            media_ids=(11, 12),
            prompt_post_url="https://t.me/channel/123",
        )
        repository = SimpleNamespace(create_media_set=AsyncMock(return_value=record))
        repository_factory = Mock(return_value=repository)
        database = SimpleNamespace()

        with patch.object(
            actions,
            "MediaSetActionsRepository",
            new=repository_factory,
        ):
            result = await actions.create_media_set_with_prompt(
                database,
                candidate_id=7,
                created_by=42,
            )

        self.assertEqual(
            result,
            CreatedMediaSet(
                id=51,
                title="KR · сет",
                media_ids=(11, 12),
                prompt_post_url="https://t.me/channel/123",
            ),
        )
        repository_factory.assert_called_once_with(database)
        repository.create_media_set.assert_awaited_once_with(
            candidate_id=7,
            created_by=42,
        )

    def test_installer_is_idempotent(self) -> None:
        original_installed = actions._INSTALLED
        original_create = actions.media_sets.create_media_set
        try:
            actions._INSTALLED = False
            actions.media_sets.create_media_set = Mock()
            actions.install_media_set_actions()
            first = actions.media_sets.create_media_set
            actions.install_media_set_actions()
            self.assertIs(first, actions.media_sets.create_media_set)
            self.assertIs(first, actions.create_media_set_with_prompt)
        finally:
            actions._INSTALLED = original_installed
            actions.media_sets.create_media_set = original_create


if __name__ == "__main__":
    unittest.main()
