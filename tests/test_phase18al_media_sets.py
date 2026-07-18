from __future__ import annotations

import importlib.util
import inspect
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import velvet_bot.media_sets as installed_media_sets

_SOURCE_MODULE_NAME = "velvet_bot._phase18al_media_sets_source"
_SOURCE_SPEC = importlib.util.spec_from_file_location(
    _SOURCE_MODULE_NAME,
    Path(installed_media_sets.__file__),
)
if _SOURCE_SPEC is None or _SOURCE_SPEC.loader is None:
    raise RuntimeError("Не удалось загрузить исходный velvet_bot/media_sets.py")
media_sets = importlib.util.module_from_spec(_SOURCE_SPEC)
sys.modules[_SOURCE_MODULE_NAME] = media_sets
_SOURCE_SPEC.loader.exec_module(media_sets)

MediaSetCandidate = media_sets.MediaSetCandidate
MediaSetCandidateItem = media_sets.MediaSetCandidateItem
_CandidateDraft = media_sets._CandidateDraft
create_media_set = media_sets.create_media_set
create_set_candidate_from_duplicate = media_sets.create_set_candidate_from_duplicate
decide_media_set_candidate = media_sets.decide_media_set_candidate
delete_duplicate_media = media_sets.delete_duplicate_media
discover_media_set_candidates = media_sets.discover_media_set_candidates
get_media_set_candidate = media_sets.get_media_set_candidate
list_media_set_candidates = media_sets.list_media_set_candidates
toggle_media_set_candidate_item = media_sets.toggle_media_set_candidate_item


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


def _candidate(candidate_id: int) -> MediaSetCandidate:
    return MediaSetCandidate(
        id=candidate_id,
        suggested_title=f"Сет {candidate_id}",
        reason="Контекст",
        score=90,
        prompt_post_url=None,
        status="pending",
        items=(
            MediaSetCandidateItem(
                media_id=11,
                telegram_file_id="file-11",
                media_type="photo",
                file_name="one.webp",
                characters=("Каэль",),
                selected=True,
                context_score=90,
                reason="Общий контекст",
            ),
        ),
    )


class MediaSetsBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_module_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(media_sets)
        self.assertNotIn("._require_pool()", source)
        self.assertEqual(9, source.count("database.acquire()"))

    async def test_discovery_preserves_two_connections_transaction_and_created_count(self) -> None:
        linked_at = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        read_connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {
                        "media_id": "11",
                        "telegram_file_id": "file-11",
                        "media_type": "photo",
                        "file_name": "kael_set.webp",
                        "linked_at": linked_at,
                        "characters": ["Каэль"],
                        "universes": ["kr"],
                        "story_ids": [5],
                        "prompt_post_url": "https://t.me/prompt/1",
                        "width": "1024",
                        "height": "1536",
                        "phash": "0f",
                    }
                ]
            )
        )
        transaction = _TransactionContext()
        write_connection = SimpleNamespace(
            fetchrow=AsyncMock(return_value={"id": "71", "inserted": True}),
            execute=AsyncMock(return_value="INSERT 0 1"),
            transaction=Mock(return_value=transaction),
        )
        database = SimpleNamespace(
            acquire=Mock(
                side_effect=[
                    _AsyncContext(read_connection),
                    _AsyncContext(write_connection),
                ]
            )
        )
        draft = _CandidateDraft(
            key="prompt:key",
            title="KR · сет",
            reason="Общий промт",
            score=100,
            prompt_post_url="https://t.me/prompt/1",
            items=((11, 100, "Общий промт"), (12, 100, "Общий промт")),
        )

        with patch.object(
            media_sets,
            "_drafts_from_contexts",
            new=Mock(return_value=(draft,)),
        ) as drafts_mock:
            result = await discover_media_set_candidates(database, limit=9999)

        self.assertEqual(result, 1)
        self.assertEqual(database.acquire.call_count, 2)
        self.assertEqual(read_connection.fetch.await_args.args[1], 600)
        contexts = drafts_mock.call_args.args[0]
        self.assertEqual(contexts[0].media_id, 11)
        self.assertEqual(contexts[0].aspect_ratio, 1024 / 1536)
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        self.assertEqual(write_connection.execute.await_count, 2)

    async def test_candidate_page_detail_toggle_and_decision_preserve_mappings(self) -> None:
        page_connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=17),
            fetch=AsyncMock(return_value=[{"id": "2"}, {"id": "3"}]),
        )
        detail_connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "id": "2",
                    "suggested_title": "KR · сет",
                    "reason": "Контекст",
                    "score": "88",
                    "prompt_post_url": None,
                    "status": "pending",
                }
            ),
            fetch=AsyncMock(
                return_value=[
                    {
                        "media_id": "11",
                        "telegram_file_id": "file-11",
                        "media_type": "photo",
                        "file_name": "one.webp",
                        "selected": True,
                        "context_score": "91",
                        "reason": "Общий контекст",
                        "characters": ["Каэль", None, "Эрик"],
                    }
                ]
            ),
        )
        toggle_connection = SimpleNamespace(fetchval=AsyncMock(return_value=False))
        decision_connection = SimpleNamespace(fetchval=AsyncMock(return_value=9))
        database = SimpleNamespace(
            acquire=Mock(
                side_effect=[
                    _AsyncContext(page_connection),
                    _AsyncContext(detail_connection),
                    _AsyncContext(toggle_connection),
                    _AsyncContext(decision_connection),
                ]
            )
        )
        detail_mock = AsyncMock(side_effect=[_candidate(2), None])

        with patch.object(media_sets, "get_media_set_candidate", new=detail_mock):
            page = await list_media_set_candidates(
                database,
                status="pending",
                page=99,
                page_size=99,
            )
        detail = await get_media_set_candidate(database, 2)
        toggled = await toggle_media_set_candidate_item(
            database,
            candidate_id="2",
            media_id="11",
        )
        decided = await decide_media_set_candidate(
            database,
            candidate_id="2",
            status="ignored",
            decided_by="42",
        )

        self.assertEqual((page.page, page.page_size, page.total_items), (2, 8, 17))
        self.assertEqual([item.id for item in page.items], [2])
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.items[0].characters, ("Каэль", "Эрик"))
        self.assertFalse(toggled)
        self.assertTrue(decided)

        invalid_database = SimpleNamespace(acquire=Mock())
        with self.assertRaisesRegex(ValueError, "Неизвестное решение"):
            await decide_media_set_candidate(
                invalid_database,
                candidate_id=2,
                status="accepted",
                decided_by=42,
            )
        invalid_database.acquire.assert_not_called()

    async def test_create_media_set_preserves_locks_prompt_and_acceptance(self) -> None:
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "id": "7",
                    "suggested_title": "KR · Каэль и Эрик",
                    "prompt_post_url": "https://t.me/prompt/1",
                    "status": "pending",
                }
            ),
            fetch=AsyncMock(return_value=[{"media_id": "11"}, {"media_id": "12"}]),
            fetchval=AsyncMock(return_value="51"),
            execute=AsyncMock(return_value="UPDATE 2"),
            transaction=Mock(return_value=transaction),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await create_media_set(database, candidate_id=7, created_by=42)

        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        self.assertEqual((result.id, result.media_ids), (51, (11, 12)))
        self.assertEqual(result.prompt_post_url, "https://t.me/prompt/1")
        self.assertIn("FOR UPDATE", connection.fetchrow.await_args.args[0])
        self.assertIn("FOR UPDATE OF mf", connection.fetch.await_args.args[0])
        self.assertEqual(connection.execute.await_count, 3)
        self.assertIn("UPDATE media_files", connection.execute.await_args_list[0].args[0])
        self.assertIn("UPDATE character_media", connection.execute.await_args_list[1].args[0])
        self.assertIn("status = 'accepted'", connection.execute.await_args_list[2].args[0])

    async def test_duplicate_conversion_preserves_score_floor_and_transaction(self) -> None:
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "first_media_id": "12",
                    "second_media_id": "11",
                    "similarity_score": "61",
                    "first_set_id": None,
                    "second_set_id": None,
                    "characters": ["Каэль", "Эрик"],
                    "prompt_post_url": None,
                }
            ),
            fetchval=AsyncMock(return_value="81"),
            execute=AsyncMock(return_value="OK"),
            transaction=Mock(return_value=transaction),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await create_set_candidate_from_duplicate(
            database,
            duplicate_candidate_id=4,
            decided_by=42,
        )

        self.assertEqual(result, 81)
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        insert_args = connection.fetchval.await_args.args
        self.assertEqual(insert_args[1], "visual:11:12")
        self.assertEqual(insert_args[2], "Сет: Каэль, Эрик")
        self.assertEqual(insert_args[4], 65)
        self.assertEqual(connection.execute.await_count, 3)

    async def test_duplicate_deletion_preserves_archive_refs_and_cascade_order(self) -> None:
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                side_effect=[
                    {"first_media_id": "11", "second_media_id": "12"},
                    {"file_name": "duplicate.webp", "media_set_id": "51"},
                ]
            ),
            fetch=AsyncMock(
                return_value=[
                    {
                        "character_name": "Каэль",
                        "archive_chat_id": "-1005",
                        "archive_message_id": "77",
                    },
                    {
                        "character_name": "Эрик",
                        "archive_chat_id": None,
                        "archive_message_id": None,
                    },
                ]
            ),
            execute=AsyncMock(return_value="OK"),
            transaction=Mock(return_value=transaction),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await delete_duplicate_media(
            database,
            duplicate_candidate_id=4,
            media_id=11,
            decided_by=42,
        )

        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        self.assertEqual(result.file_name, "duplicate.webp")
        self.assertEqual(result.characters, ("Каэль", "Эрик"))
        self.assertEqual(len(result.archive_messages), 1)
        self.assertEqual(result.archive_messages[0].message_id, 77)
        self.assertEqual(connection.execute.await_count, 8)
        sqls = [call.args[0] for call in connection.execute.await_args_list]
        self.assertIn("DELETE FROM media_duplicate_candidates", sqls[0])
        self.assertIn("DELETE FROM media_set_candidate_items", sqls[1])
        self.assertIn("DELETE FROM media_visual_fingerprints", sqls[3])
        self.assertIn("DELETE FROM media_file_checks", sqls[4])
        self.assertIn("DELETE FROM character_media", sqls[5])
        self.assertIn("DELETE FROM media_files", sqls[6])
        self.assertIn("DELETE FROM media_sets", sqls[7])


if __name__ == "__main__":
    unittest.main()
