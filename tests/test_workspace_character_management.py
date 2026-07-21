from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import (
    add_workspace_character_alias,
    create_workspace_character,
    delete_workspace_character,
    delete_workspace_character_alias,
    load_workspace_character,
    rename_workspace_character,
    set_workspace_character_prompt_url,
    set_workspace_character_topic,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_repository import WorkspaceProductRepository
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.topics import TopicReference


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceCharacterManagementContractTests(unittest.TestCase):
    def test_migration_defines_workspace_scoped_aliases(self) -> None:
        sql = (
            ROOT / "migrations/905_workspace_character_management.sql"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS workspace_character_aliases",
            sql,
        )
        self.assertIn("UNIQUE (workspace_id, normalized_alias)", sql)
        self.assertIn("REFERENCES characters(workspace_id, id)", sql)

    def test_workspace_character_router_is_registered_before_legacy_admin(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        new_index = source.index(
            "router.include_router(workspace_character_management_router)"
        )
        legacy_index = source.index("router.include_router(workspace_admin_router)")
        self.assertLess(new_index, legacy_index)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceCharacterManagementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        self.workspace_repository = WorkspaceRepository(self.database)
        self.product_repository = WorkspaceProductRepository(self.database)
        self.service = WorkspaceProductService(
            product_repository=self.product_repository,
            workspace_repository=self.workspace_repository,
        )
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

    async def _create_workspace(self, user_id: int, name: str):
        await self.service.grant_creation_access(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            user_id=user_id,
        )
        return await self.service.create_personal_workspace(
            owner_user_id=user_id,
            name=name,
        )

    async def test_aliases_are_unique_inside_workspace_but_reusable_elsewhere(self) -> None:
        first = await self._create_workspace(601, "First")
        second = await self._create_workspace(602, "Second")
        first_character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Каэль",
            created_by=601,
            created_in_chat=1001,
        )
        second_character, _ = await create_workspace_character(
            self.database,
            workspace_id=second.id,
            name="Эрик",
            created_by=602,
            created_in_chat=1002,
        )
        await add_workspace_character_alias(
            self.database,
            workspace_id=first.id,
            character_id=first_character.id,
            alias="Wolf",
            created_by=601,
        )
        await add_workspace_character_alias(
            self.database,
            workspace_id=second.id,
            character_id=second_character.id,
            alias="Wolf",
            created_by=602,
        )

        rival, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Рейнольдс",
            created_by=601,
            created_in_chat=1001,
        )
        with self.assertRaisesRegex(ValueError, "уже принадлежит"):
            await add_workspace_character_alias(
                self.database,
                workspace_id=first.id,
                character_id=rival.id,
                alias="wolf",
                created_by=601,
            )

    async def test_rename_updates_workspace_name_alias(self) -> None:
        workspace = await self._create_workspace(603, "Rename")
        character, _ = await create_workspace_character(
            self.database,
            workspace_id=workspace.id,
            name="Старое имя",
            created_by=603,
            created_in_chat=1003,
        )
        renamed = await rename_workspace_character(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            new_name="Новое имя",
        )
        self.assertEqual("Новое имя", renamed.name)
        name_aliases = [item for item in renamed.aliases if item.source == "name"]
        self.assertEqual(["Новое имя"], [item.alias for item in name_aliases])

    async def test_prompt_topic_and_manual_alias_can_be_added_and_removed(self) -> None:
        workspace = await self._create_workspace(604, "Links")
        character, _ = await create_workspace_character(
            self.database,
            workspace_id=workspace.id,
            name="Лейн",
            created_by=604,
            created_in_chat=1004,
        )
        alias = await add_workspace_character_alias(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            alias="Lane",
            created_by=604,
        )
        self.assertEqual("Lane", alias.alias)

        await set_workspace_character_prompt_url(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            prompt_post_url="https://t.me/velvetAnatomy/123",
        )
        topic = TopicReference(
            chat_id=-1003951213065,
            thread_id=1398,
            url="https://t.me/c/3951213065/1398",
        )
        await set_workspace_character_topic(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            topic=topic,
        )
        loaded = await load_workspace_character(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
        )
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual("https://t.me/velvetAnatomy/123", loaded.prompt_post_url)
        self.assertEqual(topic.url, loaded.archive_topic_url)
        self.assertIn("Lane", [item.alias for item in loaded.aliases])

        self.assertTrue(
            await delete_workspace_character_alias(
                self.database,
                workspace_id=workspace.id,
                character_id=character.id,
                alias="Lane",
            )
        )
        await set_workspace_character_prompt_url(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            prompt_post_url=None,
        )
        await set_workspace_character_topic(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            topic=None,
        )
        loaded = await load_workspace_character(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
        )
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIsNone(loaded.prompt_post_url)
        self.assertIsNone(loaded.archive_topic_url)
        self.assertNotIn("Lane", [item.alias for item in loaded.aliases])

    async def test_delete_is_scoped_and_cascades_workspace_aliases(self) -> None:
        first = await self._create_workspace(605, "Delete First")
        second = await self._create_workspace(606, "Delete Second")
        first_character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Один",
            created_by=605,
            created_in_chat=1005,
        )
        second_character, _ = await create_workspace_character(
            self.database,
            workspace_id=second.id,
            name="Два",
            created_by=606,
            created_in_chat=1006,
        )
        await add_workspace_character_alias(
            self.database,
            workspace_id=first.id,
            character_id=first_character.id,
            alias="Удалить меня",
            created_by=605,
        )

        with self.assertRaisesRegex(ValueError, "не найден"):
            await delete_workspace_character(
                self.database,
                workspace_id=second.id,
                character_id=first_character.id,
            )

        deleted = await delete_workspace_character(
            self.database,
            workspace_id=first.id,
            character_id=first_character.id,
        )
        self.assertEqual("Один", deleted.name)
        self.assertGreaterEqual(deleted.aliases, 2)
        self.assertIsNone(
            await load_workspace_character(
                self.database,
                workspace_id=first.id,
                character_id=first_character.id,
            )
        )
        self.assertIsNotNone(
            await load_workspace_character(
                self.database,
                workspace_id=second.id,
                character_id=second_character.id,
            )
        )


if __name__ == "__main__":
    unittest.main()
