from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import velvet_bot.media_set_ai_discovery as discovery
import velvet_bot.media_set_ai_repository as repository_module
from velvet_bot.media_set_ai_discovery import _AIContext
from velvet_bot.media_set_ai_repository import (
    MediaSetAICandidateDraft,
    MediaSetAICandidateItemDraft,
    MediaSetAIContextRow,
    MediaSetAIRepository,
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


class MediaSetAIRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def test_layer_boundary_is_explicit(self) -> None:
        service_source = inspect.getsource(discovery)
        repository_source = inspect.getsource(repository_module)
        self.assertNotIn("._require_pool()", service_source)
        self.assertNotIn("database.acquire()", service_source)
        self.assertNotIn("._require_pool()", repository_source)
        self.assertEqual(2, repository_source.count("self._database.acquire()"))
        self.assertIn("MediaSetAIRepository", service_source)

    async def test_load_context_rows_preserves_limit_and_mapping(self) -> None:
        connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {
                        "media_id": "11",
                        "characters": ["Каэль", None, "Эрик"],
                        "analysis": '{"themes": ["western"]}',
                        "prompt_post_url": "https://t.me/prompt/1",
                    }
                ]
            )
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await MediaSetAIRepository(database).load_context_rows(limit=9999)

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, limit = connection.fetch.await_args.args
        self.assertIn("profile.status = 'ready'", sql)
        self.assertIn("mf.media_set_id IS NULL", sql)
        self.assertEqual(limit, 1000)
        self.assertEqual(
            result,
            (
                MediaSetAIContextRow(
                    media_id=11,
                    characters=("Каэль", "Эрик"),
                    analysis='{"themes": ["western"]}',
                    prompt_post_url="https://t.me/prompt/1",
                ),
            ),
        )

    async def test_store_candidates_preserves_retirement_transaction_and_upserts(self) -> None:
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            execute=AsyncMock(return_value="OK"),
            fetchrow=AsyncMock(return_value={"id": "71", "inserted": True}),
            transaction=Mock(return_value=transaction),
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))
        draft = MediaSetAICandidateDraft(
            candidate_key="ai:key",
            suggested_title="Western duo",
            reason="Общие themes и setting",
            score=83,
            prompt_post_url="https://t.me/prompt/1",
            items=(
                MediaSetAICandidateItemDraft(
                    media_id=11,
                    context_score=81,
                    reason="ИИ-контекст: western, desert",
                ),
                MediaSetAICandidateItemDraft(
                    media_id=12,
                    context_score=85,
                    reason="ИИ-контекст: western, desert",
                ),
            ),
        )

        result = await MediaSetAIRepository(database).store_candidates((draft,))

        self.assertEqual(result, 1)
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        self.assertEqual(connection.execute.await_count, 3)
        retire_sql = connection.execute.await_args_list[0].args[0]
        self.assertIn("candidate_key LIKE 'filename:%'", retire_sql)
        self.assertIn("candidate_key LIKE 'context:%'", retire_sql)
        insert_args = connection.fetchrow.await_args.args
        self.assertEqual(
            insert_args[1:],
            (
                "ai:key",
                "Western duo",
                "Общие themes и setting",
                83,
                "https://t.me/prompt/1",
            ),
        )
        self.assertEqual(
            connection.execute.await_args_list[1].args[1:],
            (71, 11, 81, "ИИ-контекст: western, desert"),
        )
        self.assertEqual(
            connection.execute.await_args_list[2].args[1:],
            (71, 12, 85, "ИИ-контекст: western, desert"),
        )

    async def test_store_empty_candidates_keeps_transaction_without_retirement(self) -> None:
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            execute=AsyncMock(),
            fetchrow=AsyncMock(),
            transaction=Mock(return_value=transaction),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await MediaSetAIRepository(database).store_candidates(())

        self.assertEqual(result, 0)
        connection.execute.assert_not_awaited()
        connection.fetchrow.assert_not_awaited()
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)


class MediaSetAIServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_loading_decodes_profiles_and_skips_invalid_json(self) -> None:
        rows = (
            MediaSetAIContextRow(
                media_id=11,
                characters=("Каэль",),
                analysis='{"themes": ["western"]}',
                prompt_post_url=None,
            ),
            MediaSetAIContextRow(
                media_id=12,
                characters=("Эрик",),
                analysis="not-json",
                prompt_post_url="https://t.me/prompt/1",
            ),
        )
        repository = SimpleNamespace(load_context_rows=AsyncMock(return_value=rows))
        repository_factory = Mock(return_value=repository)
        database = SimpleNamespace()

        with patch.object(
            discovery,
            "MediaSetAIRepository",
            new=repository_factory,
        ):
            result = await discovery._load_ai_contexts(database, limit=77)

        repository_factory.assert_called_once_with(database)
        repository.load_context_rows.assert_awaited_once_with(limit=77)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].media_id, 11)
        self.assertEqual(result[0].profile, {"themes": ["western"]})

    def test_candidate_drafts_preserve_semantic_fields_and_item_reasons(self) -> None:
        first = _AIContext(
            media_id=11,
            characters=("Каэль",),
            profile={"themes": ["western"], "settings": ["desert"]},
            prompt_post_url="https://t.me/prompt/1",
        )
        second = _AIContext(
            media_id=12,
            characters=("Эрик",),
            profile={"themes": ["western"], "settings": ["desert"]},
            prompt_post_url="https://t.me/prompt/1",
        )
        match = SimpleNamespace(score=82, common_terms=("western", "desert"))

        with (
            patch.object(
                discovery,
                "compare_semantic_profiles",
                new=Mock(return_value=match),
            ),
            patch.object(
                discovery,
                "build_semantic_set_title",
                new=Mock(return_value="Western duo"),
            ),
            patch.object(
                discovery,
                "build_semantic_reason",
                new=Mock(return_value="Общие themes и settings"),
            ),
        ):
            drafts = discovery._candidate_drafts(((first, second),))

        self.assertEqual(len(drafts), 1)
        draft = drafts[0]
        self.assertTrue(draft.candidate_key.startswith("ai:"))
        self.assertEqual(draft.suggested_title, "Western duo")
        self.assertEqual(draft.reason, "Общие themes и settings")
        self.assertEqual(draft.score, 82)
        self.assertEqual(draft.prompt_post_url, "https://t.me/prompt/1")
        self.assertEqual([item.media_id for item in draft.items], [11, 12])
        self.assertEqual([item.context_score for item in draft.items], [82, 82])
        self.assertTrue(all("desert" in item.reason for item in draft.items))

    async def test_store_delegates_prepared_drafts_to_repository(self) -> None:
        first = _AIContext(11, ("Каэль",), {"themes": ["western"]}, None)
        second = _AIContext(12, ("Эрик",), {"themes": ["western"]}, None)
        prepared = (
            MediaSetAICandidateDraft(
                candidate_key="ai:key",
                suggested_title="Set",
                reason="Reason",
                score=80,
                prompt_post_url=None,
                items=(),
            ),
        )
        repository = SimpleNamespace(store_candidates=AsyncMock(return_value=3))
        database = SimpleNamespace()

        with (
            patch.object(
                discovery,
                "_candidate_drafts",
                new=Mock(return_value=prepared),
            ),
            patch.object(
                discovery,
                "MediaSetAIRepository",
                new=Mock(return_value=repository),
            ) as repository_factory,
        ):
            result = await discovery._store_ai_candidates(
                database,
                ((first, second),),
            )

        self.assertEqual(result, 3)
        repository_factory.assert_called_once_with(database)
        repository.store_candidates.assert_awaited_once_with(prepared)

    async def test_discovery_preserves_fallback_short_circuit_and_ai_total(self) -> None:
        database = SimpleNamespace()
        one_context = (_AIContext(11, ("Каэль",), {"themes": ["x"]}, None),)
        two_contexts = (
            _AIContext(11, ("Каэль",), {"themes": ["x"]}, None),
            _AIContext(12, ("Эрик",), {"themes": ["x"]}, None),
        )
        fallback = AsyncMock(side_effect=[2, 2])
        load = AsyncMock(side_effect=[one_context, two_contexts])
        groups = Mock(return_value=(two_contexts,))
        store = AsyncMock(return_value=4)

        with (
            patch.object(discovery, "_ORIGINAL_DISCOVER", new=fallback),
            patch.object(discovery, "_load_ai_contexts", new=load),
            patch.object(discovery, "_component_groups", new=groups),
            patch.object(discovery, "_store_ai_candidates", new=store),
        ):
            short_result = await discovery.discover_media_set_candidates_with_ai(
                database,
                limit=100,
            )
            full_result = await discovery.discover_media_set_candidates_with_ai(
                database,
                limit=100,
            )

        self.assertEqual(short_result, 2)
        self.assertEqual(full_result, 6)
        self.assertEqual(fallback.await_count, 2)
        self.assertEqual(load.await_args_list[0].kwargs, {"limit": 600})
        self.assertEqual(load.await_args_list[1].kwargs, {"limit": 600})
        groups.assert_called_once_with(two_contexts)
        store.assert_awaited_once_with(database, (two_contexts,))


if __name__ == "__main__":
    unittest.main()
