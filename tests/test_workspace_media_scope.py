from __future__ import annotations

import inspect
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.app.save_sessions import SaveUploadSessions
from velvet_bot.archive_topic_links import list_characters_by_archive_topic
from velvet_bot.character_resolution import load_character_by_id, resolve_character
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import (
    add_workspace_character_alias,
    create_workspace_character,
    set_workspace_character_topic,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.services.media_save import save_media_from_message
from velvet_bot.topics import TopicReference

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceMediaScopeContractTests(unittest.TestCase):
    def test_save_session_pins_workspace_and_character(self) -> None:
        clock = SimpleNamespace(value=100.0)
        sessions = SaveUploadSessions(
            ttl_seconds=60,
            clock=lambda: clock.value,
        )
        session = sessions.start(
            chat_id=10,
            user_id=20,
            character_name="Каэль",
            character_id=777,
            workspace_id=55,
            command_message_id=30,
        )
        self.assertEqual(55, session.workspace_id)
        self.assertEqual(777, session.character_id)
        self.assertEqual(session, sessions.get(chat_id=10, user_id=20))

    def test_media_save_api_accepts_workspace_boundary(self) -> None:
        parameters = inspect.signature(save_media_from_message).parameters
        self.assertIn("workspace_id", parameters)
        self.assertIn("resolved_character", parameters)

    def test_save_router_freezes_workspace_in_upload_session(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive/save.py"
        ).read_text(encoding="utf-8")
        self.assertIn("workspace_id=character.workspace_id", source)
        self.assertIn("character_id=character.id", source)
        self.assertIn("save_upload_session.workspace_id", source)
        self.assertIn("minimum_role=\"editor\"", source)
        self.assertIn("module_key = 'archive'", source)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceMediaScopeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        await self._reset()

    async def asyncTearDown(self) -> None:
        await self._reset()
        await self.database.close()

    async def _reset(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    workspace_character_aliases,
                    workspace_character_story_links,
                    character_archive_topics,
                    character_media,
                    media_files,
                    characters
                RESTART IDENTITY CASCADE
                """
            )
            await connection.execute(
                "DELETE FROM workspaces WHERE id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute("DELETE FROM workspace_creation_grants")
            await connection.execute("DELETE FROM user_public_workspace_preferences")
            await connection.execute("DELETE FROM user_workspace_preferences")

    async def _create_workspace(self, user_id: int, name: str):
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspaces (slug, name, is_system)
                VALUES ($1::VARCHAR, $2::VARCHAR, FALSE)
                RETURNING id
                """,
                f"media-{int(user_id)}",
                name,
            )
            if row is None:
                raise RuntimeError("Не удалось создать тестовое пространство.")
            workspace_id = int(row["id"])
            await connection.execute(
                """
                INSERT INTO workspace_members (workspace_id, user_id, role)
                VALUES ($1::BIGINT, $2::BIGINT, 'owner')
                """,
                workspace_id,
                int(user_id),
            )
            await connection.execute(
                """
                INSERT INTO workspace_modules (
                    workspace_id, module_key, is_allowed, is_enabled
                )
                VALUES ($1::BIGINT, 'archive', TRUE, TRUE)
                ON CONFLICT (workspace_id, module_key) DO UPDATE
                SET is_allowed = TRUE, is_enabled = TRUE
                """,
                workspace_id,
            )
        return SimpleNamespace(id=workspace_id)

    async def test_name_and_alias_resolution_are_isolated(self) -> None:
        first = await self._create_workspace(801, "First")
        second = await self._create_workspace(802, "Second")
        first_character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Каэль",
            created_by=801,
            created_in_chat=1801,
        )
        second_character, _ = await create_workspace_character(
            self.database,
            workspace_id=second.id,
            name="Каэль",
            created_by=802,
            created_in_chat=1802,
        )
        await add_workspace_character_alias(
            self.database,
            workspace_id=first.id,
            character_id=first_character.id,
            alias="Wolf",
            created_by=801,
        )
        await add_workspace_character_alias(
            self.database,
            workspace_id=second.id,
            character_id=second_character.id,
            alias="Wolf",
            created_by=802,
        )

        by_first_name = await resolve_character(
            self.database,
            "Каэль",
            workspace_id=first.id,
        )
        by_second_alias = await resolve_character(
            self.database,
            "wolf",
            workspace_id=second.id,
        )
        self.assertIsNotNone(by_first_name)
        self.assertIsNotNone(by_second_alias)
        assert by_first_name is not None
        assert by_second_alias is not None
        self.assertEqual(first_character.id, by_first_name.id)
        self.assertEqual(second_character.id, by_second_alias.id)
        self.assertEqual(first.id, by_first_name.workspace_id)
        self.assertEqual(second.id, by_second_alias.workspace_id)

        self.assertIsNone(
            await load_character_by_id(
                self.database,
                character_id=first_character.id,
                workspace_id=second.id,
            )
        )

    async def test_archive_chat_selects_only_its_workspace_characters(self) -> None:
        first = await self._create_workspace(803, "Archive First")
        second = await self._create_workspace(804, "Archive Second")
        first_character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Эрик",
            created_by=803,
            created_in_chat=1803,
        )
        second_character, _ = await create_workspace_character(
            self.database,
            workspace_id=second.id,
            name="Рейнольдс",
            created_by=804,
            created_in_chat=1804,
        )
        topic = TopicReference(
            chat_id=-100555000111,
            thread_id=88,
            url="https://t.me/c/555000111/88",
        )
        await set_workspace_character_topic(
            self.database,
            workspace_id=first.id,
            character_id=first_character.id,
            topic=topic,
        )
        await set_workspace_character_topic(
            self.database,
            workspace_id=second.id,
            character_id=second_character.id,
            topic=topic,
        )
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO workspace_channels (workspace_id, kind, chat_id)
                VALUES ($1::BIGINT, 'archive', $2::BIGINT)
                """,
                first.id,
                topic.chat_id,
            )

        characters = await list_characters_by_archive_topic(
            self.database,
            archive_chat_id=topic.chat_id,
            archive_thread_id=topic.thread_id,
        )
        self.assertEqual([first_character.id], [item.id for item in characters])
        self.assertEqual([first.id], [item.workspace_id for item in characters])

    async def test_unconfigured_archive_chat_falls_back_to_system_workspace(self) -> None:
        system_character, _ = await self.database.create_character(
            "Системный",
            created_by=805,
            created_in_chat=1805,
            workspace_id=DEFAULT_WORKSPACE_ID,
        )
        personal = await self._create_workspace(806, "Personal")
        personal_character, _ = await create_workspace_character(
            self.database,
            workspace_id=personal.id,
            name="Личный",
            created_by=806,
            created_in_chat=1806,
        )
        topic = TopicReference(
            chat_id=-100777000222,
            thread_id=99,
            url="https://t.me/c/777000222/99",
        )
        async with self.database.acquire() as connection:
            for character_id in (system_character.id, personal_character.id):
                await connection.execute(
                    """
                    INSERT INTO character_archive_topics (
                        character_id, archive_chat_id, archive_thread_id, archive_topic_url
                    )
                    VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT, $4::TEXT)
                    """,
                    character_id,
                    topic.chat_id,
                    topic.thread_id,
                    topic.url,
                )

        characters = await list_characters_by_archive_topic(
            self.database,
            archive_chat_id=topic.chat_id,
            archive_thread_id=topic.thread_id,
        )
        self.assertEqual([system_character.id], [item.id for item in characters])
        self.assertEqual(
            [DEFAULT_WORKSPACE_ID],
            [item.workspace_id for item in characters],
        )


if __name__ == "__main__":
    unittest.main()
