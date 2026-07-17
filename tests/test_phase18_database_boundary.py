from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.database import Database
from velvet_bot.domains.discussions import (
    DiscussionIngestRepository,
    DiscussionMessageEvent,
    DiscussionRepository,
)
from velvet_bot.domains.media_quality import MediaQualityRepository
from velvet_bot.domains.publication import PublicationRepository
from velvet_bot.domains.references import ReferenceMediaPayload, ReferenceRepository


ROOT = Path(__file__).resolve().parents[1]


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


class DatabaseAcquireBoundaryTests(unittest.TestCase):
    def test_acquire_delegates_to_initialized_pool(self) -> None:
        database = Database("postgresql://unused")
        pool = Mock()
        context = object()
        pool.acquire.return_value = context
        database._pool = pool

        self.assertIs(database.acquire(), context)
        pool.acquire.assert_called_once_with()

    def test_acquire_rejects_uninitialized_database(self) -> None:
        database = Database("postgresql://unused")

        with self.assertRaisesRegex(RuntimeError, "ещё не инициализировано"):
            database.acquire()

    def test_migrated_domain_repositories_use_public_boundary(self) -> None:
        paths = (
            ROOT / "velvet_bot/domains/characters/repository.py",
            ROOT / "velvet_bot/domains/stories/repository.py",
            ROOT / "velvet_bot/domains/archive/repository.py",
            ROOT / "velvet_bot/domains/public_archive/repository.py",
            ROOT / "velvet_bot/domains/references/repository.py",
            ROOT / "velvet_bot/domains/media_quality/repository.py",
            ROOT / "velvet_bot/domains/publication/repository.py",
            ROOT / "velvet_bot/domains/discussions/repository.py",
            ROOT / "velvet_bot/domains/discussions/ingest_repository.py",
        )
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("._require_pool()", source)
                self.assertIn("self._database.acquire()", source)


class ReferenceRepositoryAcquireTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_uses_public_acquire_and_preserves_transaction(self) -> None:
        created_at = datetime(2026, 7, 17, tzinfo=UTC)
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "reference_id": 13,
                    "character_id": 7,
                    "telegram_file_id": "file-new",
                    "telegram_file_unique_id": "unique-7",
                    "added_by": 11,
                    "reference_created_at": created_at,
                }
            ),
            fetchval=AsyncMock(return_value=1),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = ReferenceRepository(database)

        result = await repository.add(
            character_id=7,
            media=ReferenceMediaPayload("file-new", "unique-7"),
            added_by=11,
        )

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        self.assertTrue(result.created)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.reference.id, 13)
        self.assertEqual(result.reference.telegram_file_id, "file-new")
        self.assertEqual(result.reference.created_at, created_at)


class MediaQualityRepositoryAcquireTests(unittest.IsolatedAsyncioTestCase):
    async def test_claim_uses_public_acquire_and_keeps_locked_transaction(self) -> None:
        rows = [
            {
                "id": 17,
                "scan_file_id": "preview-17",
                "display_name": "image-17.png",
            },
            {
                "id": 19,
                "scan_file_id": "file-19",
                "display_name": "image-19.jpg",
            },
        ]
        connection = SimpleNamespace(
            fetch=AsyncMock(return_value=rows),
            execute=AsyncMock(return_value="UPDATE 2"),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = MediaQualityRepository(database)

        targets = await repository.claim_pending_images(limit=99)

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        select_sql = connection.fetch.await_args.args[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", select_sql)
        self.assertEqual(connection.fetch.await_args.args[1], 5)
        connection.execute.assert_awaited_once()
        self.assertEqual(connection.execute.await_args.args[1], [17, 19])
        self.assertEqual([target.media_id for target in targets], [17, 19])
        self.assertEqual(targets[0].telegram_file_id, "preview-17")
        self.assertEqual(targets[1].display_name, "image-19.jpg")


class PublicationRepositoryAcquireTests(unittest.IsolatedAsyncioTestCase):
    async def test_mark_published_uses_public_acquire_and_logs_in_transaction(self) -> None:
        connection = SimpleNamespace(
            execute=AsyncMock(return_value="UPDATE 1"),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = PublicationRepository(database)

        await repository.mark_published(
            23,
            message_ids=[101, 102],
            actor_id=7,
        )

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        self.assertEqual(connection.execute.await_count, 2)

        update_call = connection.execute.await_args_list[0]
        self.assertIn("status = 'published'", update_call.args[0])
        self.assertEqual(update_call.args[1], 23)
        self.assertEqual(update_call.args[2], [101, 102])

        event_call = connection.execute.await_args_list[1]
        self.assertIn("INSERT INTO publication_events", event_call.args[0])
        self.assertEqual(event_call.args[1], 23)
        self.assertEqual(event_call.args[2], "published")
        self.assertEqual(event_call.args[3], 7)
        self.assertIn('"message_ids": [101, 102]', event_call.args[4])


class DiscussionRepositoryAcquireTests(unittest.IsolatedAsyncioTestCase):
    async def test_reaction_delta_uses_public_acquire_and_locked_transaction(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(side_effect=[1, 1]),
            fetchrow=AsyncMock(
                return_value={"reaction_breakdown": '{"👍": 2, "🔥": 1}'}
            ),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = DiscussionRepository(database)

        updated = await repository.apply_reaction_delta(
            discussion_chat_id=-10077,
            discussion_message_id=55,
            delta={"👍": -1, "🔥": 2, "❤️": 1, "ignored": 0},
        )

        self.assertTrue(updated)
        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)

        tracked_call = connection.fetchval.await_args_list[0]
        self.assertIn("source_kind = 'discussion'", tracked_call.args[0])
        self.assertEqual(tracked_call.args[1], -10077)

        locked_sql = connection.fetchrow.await_args.args[0]
        self.assertIn("FOR UPDATE", locked_sql)
        self.assertEqual(connection.fetchrow.await_args.args[1:], (-10077, 55))

        update_call = connection.fetchval.await_args_list[1]
        self.assertIn("UPDATE channel_posts", update_call.args[0])
        self.assertEqual(update_call.args[1], -10077)
        self.assertEqual(update_call.args[2], 55)
        self.assertEqual(update_call.args[3], 5)
        self.assertIn('"👍": 1', update_call.args[4])
        self.assertIn('"🔥": 3', update_call.args[4])
        self.assertIn('"❤️": 1', update_call.args[4])


class DiscussionIngestRepositoryAcquireTests(unittest.IsolatedAsyncioTestCase):
    async def test_store_message_uses_public_acquire_and_preserves_transaction(self) -> None:
        posted_at = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
        event = DiscussionMessageEvent(
            chat_id=-10088,
            chat_title="Velvet discussion",
            chat_username="velvet_discussion",
            message_id=71,
            posted_at=posted_at,
            edited_at=None,
            sender_is_bot=False,
            sender_id="42",
            sender_name="Author",
            text_content="Archive comment",
            media_group_id=None,
            media_type="text",
            has_spoiler=False,
            reply_to_message_id=None,
            reply_text="",
            reply_date=None,
            reply_is_automatic_forward=False,
            topic_id=None,
            is_automatic_forward=False,
            forward_channel_id=None,
            forward_message_id=None,
        )
        connection = SimpleNamespace(
            fetch=AsyncMock(return_value=[]),
            fetchval=AsyncMock(return_value=31),
            execute=AsyncMock(return_value="UPDATE 1"),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = DiscussionIngestRepository(database)

        stored = await repository.store_message(
            event,
            parent_channel_id=-1001,
            source_channel_message_id=None,
            root_message_id=None,
            is_root=False,
            publication_key="discussion:-10088:71",
            is_prompt=False,
            prompt_score=0,
            has_important=False,
            has_strict=False,
            has_negative=False,
            has_technical=False,
            has_palette=False,
            hashtags=(),
            links=(),
        )

        self.assertTrue(stored)
        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        connection.fetch.assert_awaited_once_with(
            "SELECT id, normalized_name FROM characters"
        )
        insert_call = connection.fetchval.await_args
        self.assertIn("INSERT INTO channel_posts", insert_call.args[0])
        self.assertEqual(insert_call.args[1], -10088)
        self.assertEqual(insert_call.args[2], 71)
        self.assertEqual(insert_call.args[3], "discussion:-10088:71")
        self.assertEqual(connection.execute.await_count, 3)
        self.assertIn("UPDATE tracked_channels", connection.execute.await_args_list[0].args[0])
        self.assertIn("DELETE FROM channel_post_hashtags", connection.execute.await_args_list[1].args[0])
        self.assertIn("DELETE FROM channel_post_links", connection.execute.await_args_list[2].args[0])


if __name__ == "__main__":
    unittest.main()
