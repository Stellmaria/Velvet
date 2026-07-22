from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.workspaces.character_topics import (
    ensure_character_archive_topic,
)


class _Database:
    def __init__(self, destination) -> None:
        self.destination = destination
        self.connection = SimpleNamespace(
            fetchrow=AsyncMock(return_value=destination),
        )

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def _character(**overrides):
    values = {
        "id": 91,
        "name": "Каэль Лэнг",
        "archive_chat_id": None,
        "archive_thread_id": None,
        "archive_topic_url": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class WorkspaceCharacterTopicProvisioningTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_and_binds_topic_from_characters_destination(self) -> None:
        database = _Database(
            {
                "chat_id": -1004459280894,
                "can_manage_topics": True,
                "bot_status": "administrator",
            }
        )
        bot = SimpleNamespace(
            create_forum_topic=AsyncMock(
                return_value=SimpleNamespace(message_thread_id=77)
            ),
            delete_forum_topic=AsyncMock(),
        )
        bind = AsyncMock()

        with patch(
            "velvet_bot.domains.workspaces.character_topics.bind_character_archive_topic",
            new=bind,
        ):
            result = await ensure_character_archive_topic(
                bot=bot,
                database=database,
                workspace_id=12,
                character=_character(),
            )

        self.assertTrue(result.linked)
        self.assertTrue(result.created)
        self.assertIsNotNone(result.topic)
        assert result.topic is not None
        self.assertEqual(-1004459280894, result.topic.chat_id)
        self.assertEqual(77, result.topic.thread_id)
        self.assertEqual("https://t.me/c/4459280894/77", result.topic.url)
        bot.create_forum_topic.assert_awaited_once_with(
            chat_id=-1004459280894,
            name="Каэль Лэнг",
        )
        bind.assert_awaited_once()
        bot.delete_forum_topic.assert_not_awaited()

    async def test_existing_character_topic_is_reused(self) -> None:
        database = _Database(None)
        bot = SimpleNamespace(create_forum_topic=AsyncMock())

        result = await ensure_character_archive_topic(
            bot=bot,
            database=database,
            workspace_id=12,
            character=_character(
                archive_chat_id=-1004459280894,
                archive_thread_id=88,
                archive_topic_url="https://t.me/c/4459280894/88",
            ),
        )

        self.assertTrue(result.linked)
        self.assertFalse(result.created)
        bot.create_forum_topic.assert_not_awaited()
        database.connection.fetchrow.assert_not_awaited()

    async def test_missing_destination_keeps_character_without_topic(self) -> None:
        database = _Database(None)
        bot = SimpleNamespace(create_forum_topic=AsyncMock())

        result = await ensure_character_archive_topic(
            bot=bot,
            database=database,
            workspace_id=12,
            character=_character(),
        )

        self.assertFalse(result.linked)
        self.assertIn("не подключён форум", result.error or "")
        bot.create_forum_topic.assert_not_awaited()

    async def test_database_binding_failure_removes_orphan_topic(self) -> None:
        database = _Database(
            {
                "chat_id": -1004459280894,
                "can_manage_topics": True,
                "bot_status": "administrator",
            }
        )
        bot = SimpleNamespace(
            create_forum_topic=AsyncMock(
                return_value=SimpleNamespace(message_thread_id=99)
            ),
            delete_forum_topic=AsyncMock(),
        )

        with patch(
            "velvet_bot.domains.workspaces.character_topics.bind_character_archive_topic",
            new=AsyncMock(side_effect=RuntimeError("database unavailable")),
        ):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                await ensure_character_archive_topic(
                    bot=bot,
                    database=database,
                    workspace_id=12,
                    character=_character(),
                )

        bot.delete_forum_topic.assert_awaited_once_with(
            chat_id=-1004459280894,
            message_thread_id=99,
        )


class WorkspaceCharacterTopicRouterContractTests(unittest.TestCase):
    def test_topic_creation_router_precedes_broad_character_router(self) -> None:
        source = open(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py",
            encoding="utf-8",
        ).read()
        automatic = source.index(
            "router.include_router(workspace_character_topic_creation_router)"
        )
        broad = source.index(
            "router.include_router(workspace_character_management_router)"
        )
        self.assertLess(automatic, broad)

    def test_create_handler_uses_configured_forum_topic_service(self) -> None:
        source = open(
            "velvet_bot/presentation/telegram/routers/"
            "workspace_character_topic_creation.py",
            encoding="utf-8",
        ).read()
        self.assertIn("ensure_character_archive_topic", source)
        self.assertIn("WorkspaceForm.waiting_character_command", source)
        self.assertIn("Новые сохранённые материалы", source)


if __name__ == "__main__":
    unittest.main()
