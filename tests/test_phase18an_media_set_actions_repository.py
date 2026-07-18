from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import velvet_bot.media_set_actions as actions
import velvet_bot.media_set_actions_repository as repository_module
from velvet_bot.media_set_actions_repository import MediaSetActionsRepository
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

    async def test_create_wrapper_propagates_existing_prompt_and_preserves_result(self) -> None:
        created = CreatedMediaSet(
            id=51,
            title="KR · сет",
            media_ids=(11, 12),
            prompt_post_url="https://t.me/channel/123",
        )
        original_create = AsyncMock(return_value=created)
        set_prompt = AsyncMock(return_value=created.prompt_post_url)
        database = SimpleNamespace()

        with (
            patch.object(actions, "_ORIGINAL_CREATE_MEDIA_SET", new=original_create),
            patch.object(actions, "set_media_set_prompt", new=set_prompt),
        ):
            result = await actions.create_media_set_with_prompt(
                database,
                candidate_id=7,
                created_by=42,
            )

        self.assertEqual(result, created)
        original_create.assert_awaited_once_with(
            database,
            candidate_id=7,
            created_by=42,
        )
        set_prompt.assert_awaited_once_with(
            database,
            media_set_id=51,
            prompt_post_url="https://t.me/channel/123",
        )

    async def test_create_wrapper_skips_repository_when_prompt_is_missing(self) -> None:
        created = CreatedMediaSet(
            id=52,
            title="Новый сет",
            media_ids=(21, 22),
            prompt_post_url=None,
        )
        original_create = AsyncMock(return_value=created)
        set_prompt = AsyncMock()
        database = SimpleNamespace()

        with (
            patch.object(actions, "_ORIGINAL_CREATE_MEDIA_SET", new=original_create),
            patch.object(actions, "set_media_set_prompt", new=set_prompt),
        ):
            result = await actions.create_media_set_with_prompt(
                database,
                candidate_id=8,
                created_by=42,
            )

        self.assertEqual(result, created)
        set_prompt.assert_not_awaited()

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
