from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.domains.publication.models import PublicationIssue
from velvet_bot.domains.publication.validation_repository import (
    PublicationValidationRepository,
)


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


class PublicationValidationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        path = ROOT / "velvet_bot/domains/publication/validation_repository.py"
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 2)

    async def test_load_context_preserves_queries_and_mapping(self) -> None:
        character_rows = [
            {
                "id": 3,
                "name": "Каин",
                "category": "мужской",
                "universe": "КР",
                "story_id": 9,
                "has_multi_story": True,
                "normalized_alias": "каин",
            }
        ]
        connection = SimpleNamespace(
            fetch=AsyncMock(return_value=character_rows),
            fetchrow=AsyncMock(
                side_effect=[
                    {"id": 11, "status": "scheduled"},
                    {"message_id": 22, "message_url": "https://t.me/example/22"},
                ]
            ),
        )
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = PublicationValidationRepository(database)
        draft = SimpleNamespace(
            id=7,
            target_chat_id=-1001,
            content_hash="a" * 64,
        )

        result = await repository.load_context(
            draft,
            normalized_aliases=["каин"],
            text="publication text",
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.fetch.assert_awaited_once()
        self.assertIn("FROM character_aliases AS a", connection.fetch.await_args.args[0])
        self.assertEqual(connection.fetch.await_args.args[1], ["каин"])
        self.assertEqual(connection.fetchrow.await_count, 2)
        duplicate_draft_call, duplicate_post_call = connection.fetchrow.await_args_list
        self.assertIn("FROM publication_drafts", duplicate_draft_call.args[0])
        self.assertEqual(duplicate_draft_call.args[1:], (-1001, "a" * 64, 7))
        self.assertIn("FROM channel_posts", duplicate_post_call.args[0])
        self.assertEqual(duplicate_post_call.args[1:], (-1001, "publication text"))
        self.assertEqual(result.characters[0].id, 3)
        self.assertEqual(result.characters[0].normalized_alias, "каин")
        self.assertTrue(result.characters[0].has_multi_story)
        self.assertEqual(result.duplicate_draft.id, 11)
        self.assertEqual(result.duplicate_post.message_id, 22)

    async def test_save_result_preserves_transaction_and_event(self) -> None:
        connection = SimpleNamespace(
            execute=AsyncMock(side_effect=["UPDATE 1", "INSERT 0 1"]),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = PublicationValidationRepository(database)
        expected_draft = object()
        repository._drafts = SimpleNamespace(
            get_draft=AsyncMock(return_value=expected_draft)
        )
        draft = SimpleNamespace(id=7, status="draft")
        issues = [
            PublicationIssue("missing", "error", "Ошибка", "Нет поля"),
            PublicationIssue("style", "warning", "Предупреждение", "Проверьте стиль"),
        ]

        result = await repository.save_result(
            draft,
            owner_id=8179531132,
            post_type="media",
            issues=issues,
        )

        self.assertIs(result, expected_draft)
        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        self.assertEqual(connection.execute.await_count, 2)

        update_call, event_call = connection.execute.await_args_list
        self.assertIn("UPDATE publication_drafts", update_call.args[0])
        self.assertEqual(update_call.args[1], 7)
        self.assertEqual(update_call.args[2], "checked")
        self.assertEqual(update_call.args[3], "media")
        self.assertEqual(update_call.args[4], "failed")
        self.assertEqual(update_call.args[5:7], (1, 1))
        validation_report = json.loads(update_call.args[7])
        self.assertEqual([item["severity"] for item in validation_report], ["error", "warning"])
        self.assertEqual(update_call.args[8], 8179531132)

        self.assertIn("INSERT INTO publication_events", event_call.args[0])
        self.assertEqual(event_call.args[1:3], (7, 8179531132))
        event_details = json.loads(event_call.args[3])
        self.assertEqual(
            event_details,
            {"status": "failed", "errors": 1, "warnings": 1},
        )
        repository._drafts.get_draft.assert_awaited_once_with(
            7,
            owner_id=8179531132,
        )


if __name__ == "__main__":
    unittest.main()
