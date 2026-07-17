from __future__ import annotations

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.domains.publication.draft_repository import PublicationDraftRepository
from velvet_bot.domains.publication.models import (
    PublicationInboxItem,
    PublicationInboxPayload,
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


def _payload(
    *,
    message_id: int = 11,
    media_group_id: str | None = "group-1",
    file_id: str | None = "file-1",
    text: str = "caption",
) -> PublicationInboxPayload:
    return PublicationInboxPayload(
        owner_id=8179531132,
        source_chat_id=-1001,
        source_message_id=message_id,
        media_group_id=media_group_id,
        text_content=text,
        telegram_file_id=file_id,
        telegram_file_unique_id=(f"unique-{message_id}" if file_id else None),
        media_type="photo" if file_id else "text",
        mime_type="image/jpeg" if file_id else None,
        file_name=f"image-{message_id}.jpg" if file_id else None,
        file_size=2048 if file_id else None,
        has_spoiler=True,
    )


class PublicationDraftBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary_for_all_operations(self) -> None:
        source = inspect.getsource(PublicationDraftRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 8)

        for method_name in (
            "capture_inbox",
            "list_source_items",
            "create_draft",
            "set_spoiler",
            "update_text",
            "schedule",
            "cancel",
            "retry",
        ):
            method_source = inspect.getsource(
                getattr(PublicationDraftRepository, method_name)
            )
            self.assertIn("self._database.acquire()", method_source, method_name)

        for method_name in (
            "create_draft",
            "set_spoiler",
            "update_text",
            "schedule",
            "cancel",
        ):
            method_source = inspect.getsource(
                getattr(PublicationDraftRepository, method_name)
            )
            self.assertIn("connection.transaction()", method_source, method_name)

    async def test_capture_inbox_uses_public_acquire_and_preserves_upsert(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="INSERT 0 1"))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = PublicationDraftRepository(database)
        payload = _payload()

        await repository.capture_inbox(payload)

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.execute.assert_awaited_once()
        sql, *arguments = connection.execute.await_args.args
        self.assertIn("INSERT INTO publication_inbox_items", sql)
        self.assertIn("ON CONFLICT", sql)
        self.assertEqual(arguments[0:5], [8179531132, -1001, 11, "group-1", "caption"])
        self.assertEqual(arguments[5], "file-1")
        self.assertTrue(arguments[-1])

    async def test_empty_inbox_payload_does_not_acquire_connection(self) -> None:
        database = SimpleNamespace(acquire=Mock())
        repository = PublicationDraftRepository(database)

        await repository.capture_inbox(
            _payload(media_group_id=None, file_id=None, text="")
        )

        database.acquire.assert_not_called()

    async def test_list_source_items_preserves_group_query_and_mapping(self) -> None:
        row = {
            "id": 5,
            "owner_id": 8179531132,
            "source_chat_id": -1001,
            "source_message_id": 11,
            "media_group_id": "group-1",
            "text_content": "caption",
            "telegram_file_id": "file-1",
            "telegram_file_unique_id": "unique-11",
            "media_type": "photo",
            "mime_type": "image/jpeg",
            "file_name": "image-11.jpg",
            "file_size": 2048,
            "has_spoiler": True,
        }
        connection = SimpleNamespace(fetch=AsyncMock(return_value=[row]))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = PublicationDraftRepository(database)

        result = await repository.list_source_items(_payload())

        database.acquire.assert_called_once_with()
        connection.fetch.assert_awaited_once()
        sql, *arguments = connection.fetch.await_args.args
        self.assertIn("media_group_id = $3::TEXT", sql)
        self.assertIn("ORDER BY source_message_id", sql)
        self.assertEqual(arguments, [8179531132, -1001, "group-1"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, 5)
        self.assertEqual(result[0].payload.telegram_file_id, "file-1")
        self.assertTrue(result[0].payload.has_spoiler)

    async def test_create_draft_preserves_single_transaction_items_and_event(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=41),
            execute=AsyncMock(side_effect=["INSERT 0 1", "INSERT 0 1"]),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = PublicationDraftRepository(database)
        expected_draft = object()
        repository._drafts = SimpleNamespace(
            get_draft=AsyncMock(return_value=expected_draft)
        )
        source = _payload()
        items = (
            PublicationInboxItem(id=5, payload=source),
            PublicationInboxItem(
                id=6,
                payload=_payload(
                    message_id=12,
                    media_group_id="group-1",
                    file_id=None,
                    text="text-only",
                ),
            ),
        )

        result = await repository.create_draft(
            source=source,
            target_chat_id=-1002,
            text_content="final text",
            post_type="media",
            content_hash="a" * 64,
            has_spoiler=True,
            items=items,
        )

        self.assertIs(result, expected_draft)
        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(transaction_context.entered)
        connection.fetchval.assert_awaited_once()
        draft_sql, *draft_arguments = connection.fetchval.await_args.args
        self.assertIn("INSERT INTO publication_drafts", draft_sql)
        self.assertEqual(draft_arguments[0:2], [8179531132, -1002])
        self.assertEqual(draft_arguments[-1], "a" * 64)
        self.assertEqual(connection.execute.await_count, 2)

        item_call, event_call = connection.execute.await_args_list
        self.assertIn("INSERT INTO publication_draft_items", item_call.args[0])
        self.assertEqual(item_call.args[1:4], (41, 0, "file-1"))
        self.assertIn("INSERT INTO publication_events", event_call.args[0])
        self.assertEqual(event_call.args[1:4], (41, "created", 8179531132))
        self.assertEqual(
            json.loads(event_call.args[4]),
            {"source_message_id": 11},
        )
        repository._drafts.get_draft.assert_awaited_once_with(
            41,
            owner_id=8179531132,
        )

    async def test_retry_preserves_error_status_guard(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = PublicationDraftRepository(database)

        await repository.retry(41, owner_id=8179531132)

        database.acquire.assert_called_once_with()
        sql, *arguments = connection.execute.await_args.args
        self.assertIn("status = 'checked'", sql)
        self.assertIn("AND status = 'error'", sql)
        self.assertEqual(arguments, [41, 8179531132])


if __name__ == "__main__":
    unittest.main()
