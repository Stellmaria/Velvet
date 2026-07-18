from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import velvet_bot.media_sets as media_sets
from velvet_bot.media_sets import (
    MediaSetCandidate,
    MediaSetCandidateItem,
    _CandidateDraft,
    create_media_set,
    create_set_candidate_from_duplicate,
    decide_media_set_candidate,
    delete_duplicate_media,
    discover_media_set_candidates,
    get_media_set_candidate,
    list_media_set_candidates,
    toggle_media_set_candidate_item,
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

    async def test_discovery_preserves_limit_draft_transaction_and_created_count(self) -> None:
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

        with patch(
            "velvet_bot.media_sets._drafts_from_contexts",
            new=Mock(return_value=(draft,)),
        ) as drafts_mock:
            result = await discover_media_set_candidates(database, limit=9999)

        self.assertEqual(result, 1)
        self.assertEqual(database.acquire.call_count, 2)
        sql, safe_limit = read_connection.fetch.await_args.args
        self.assertIn("mf.media_set_id IS NULL", sql)
        self.assertEqual(safe_limit, 600)
        contexts = drafts_mock.call_args.args[0]
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].media_id, 11)
        self.assertEqual(contexts[0].aspect_ratio, 1024 / 1536)
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        self.assertEqual(write_connection.execute.await_count, 2)
        first_item_args = write_connection.execute.await_args_list[0].args
        second_item_args = write_connection.execute.await_args_list[1].args
        self.assertEqual(first_item_args[1:], (71, 11, 100, "Общий промт"))
        self.assertEqual(second_item_args[1:], (71, 12, 100, "Общий промт"))

    async def test_candidate_page_preserves_clamp_and_detail_delegation(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=17),
            fetch=AsyncMock(return_value=[{"id": "2"}, {"id": "3"}]),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))
        detail_mock = AsyncMock(side_effect=[_candidate(2), None])

        with patch(
            "velvet_bot.media_sets.get_media_set_candidate",
            new=detail_mock,
        ):
            result = await list_media_set_candidates(
                database,
                status="pending",
                page=99,
                page_size=99,
            )

        self.assertEqual((result.page, result.page_size, result.total_items), (2, 8, 17))
        self.assertEqual([item.id for item in result.items], [2])
        sql, status, offset, limit = connection.fetch.await_args.args
        self.assertIn("ORDER BY score DESC, id", sql)
        self.assertEqual((status, offset, limit), ("pending", 16, 8))
        self.assertEqual(detail_mock.await_count, 2)

    async def test_candidate_detail_preserves_item_mapping(self) -> None:
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "id": "7",
                    "suggested_title": "KR · сет",
                    "reason": "Контекст",
                    "score": "88",
                    "prompt_post_url": "https://t.me/prompt/1",
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
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await get_media_set_candidate(database, 7)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((result.id, result.score, result.selected_count), (7, 88, 1))
        item = result.items[0]
        self.assertEqual(item.media_id, 11)
        self.assertEqual(item.characters, ("Каэль", "Эрик"))
        self.assertEqual(item.context_score, 91)

    async def test_toggle_and_decision_preserve_result_mapping_and_validation(self) -> None:
        toggle_connection = SimpleNamespace(fetchval=AsyncMock(return_value=False))
        decision_connection = SimpleNamespace(fetchval=AsyncMock(return_value=9))
        database = SimpleNamespace(
            acquire=Mock(
                side_effect=[
                    _AsyncContext(toggle_connection),
                    _AsyncContext(decision_connection),
                ]
            )
        )

        toggled = await toggle_media_set_candidate_item(
            database,
            candidate_id="7",
            media_id="11",
        )
        decided = await decide_media_set_candidate(
            database,
            candidate_id="7",
            status="ignored",
            decided_by="42",
        )

        self.assertFalse(toggled)
        self.assertTrue(decided)
        self.assertEqual(toggle_connection.fetchval.await_args.args[1:], (7, 11))
        self.assertEqual(decision_connection.fetchval.await_args.args[1:], (7, "ignored", 42))

        invalid_database = SimpleNamespace(acquire=Mock())
        with self.assertRaisesRegex(ValueError, "Неизвестное решение"):
            await decide_media_set_candidate(
                invalid_database,
                candidate_id=7,
                status="accepted",
                decided_by=42,
            )
        invalid_database.acquire.assert_not_called()

    async def test_create_media_set_preserves_lock_transaction_and_prompt_propagation(self) -> None:
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

    async def test_duplicate_pair_conversion_preserves_transaction_and_score_floor(self) -> None:
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
        self.assertEqual(connection.execute.await_args_list[0].args[1:4], (81, 11, 65))
        self.assertEqual(connection.execute.await_args_list[1].args[1:4], (81, 12, 65))
        self.assertIn("UPDATE media_duplicate_candidates", connection.execute.await_args_list[2].args[0])

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
        self.assertEqual(result.media_id, 11)
        self.assertEqual(result.file_name, "duplicate.webp")
        self.assertEqual(result.characters, ("Каэль", "Эрик"))
        self.assertEqual(len(result.archive_messages), 1)
        self.assertEqual(result.archive_messages[0].chat_id, -1005)
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
