from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
)
from velvet_bot.domains.workspaces.product_repository import WorkspaceProductRepository
from velvet_bot.domains.workspaces.product_service import (
    WorkspaceCreationAccessError,
    WorkspaceModuleAccessError,
    WorkspaceProductService,
)
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.workspace_ui import (
    MODULE_HELP,
    build_modules_keyboard,
    build_start_keyboard,
)

ROOT = Path(__file__).resolve().parents[1]
_TEST_KR_STORY_KEY = "workspace-test-template"


class WorkspaceProductContractTests(unittest.TestCase):
    def test_migration_defines_product_access_and_taxonomy(self) -> None:
        sql = (ROOT / "migrations/903_workspace_product_access.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_creation_grants", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_modules", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_categories", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_universes", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_stories", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS user_public_workspace_preferences", sql)
        self.assertIn("UPDATE workspace_settings", sql)
        self.assertIn("WHERE workspace_id = 1", sql)

    def test_start_keyboard_only_shows_create_when_granted(self) -> None:
        without_grant = build_start_keyboard(can_create=False, has_workspace=False)
        with_grant = build_start_keyboard(can_create=True, has_workspace=False)
        with_workspace = build_start_keyboard(can_create=False, has_workspace=True)

        self.assertEqual(1, len(without_grant.inline_keyboard))
        self.assertTrue(
            any(
                "Создать свой архив" in button.text
                for row in with_grant.inline_keyboard
                for button in row
            )
        )
        self.assertTrue(
            any(
                "Моё пространство" in button.text
                for row in with_workspace.inline_keyboard
                for button in row
            )
        )

    def test_every_module_has_help_text(self) -> None:
        self.assertEqual(set(WORKSPACE_MODULE_KEYS), set(MODULE_HELP))
        self.assertTrue(all(value.strip() for value in MODULE_HELP.values()))


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceProductTests(unittest.IsolatedAsyncioTestCase):
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
                "TRUNCATE character_media, media_files, characters RESTART IDENTITY CASCADE"
            )
            await connection.execute(
                "DELETE FROM workspaces WHERE id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute("DELETE FROM workspace_creation_grants")
            await connection.execute("DELETE FROM user_public_workspace_preferences")

    async def test_only_global_creator_can_grant_creation_access(self) -> None:
        with self.assertRaises(WorkspaceCreationAccessError):
            await self.service.grant_creation_access(
                actor_user_id=999,
                user_id=700,
            )
        grant = await self.service.grant_creation_access(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            user_id=700,
        )
        self.assertEqual(700, grant.user_id)
        self.assertEqual(1, grant.max_workspaces)

    async def test_personal_workspace_is_private_and_module_gated(self) -> None:
        await self.service.grant_creation_access(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            user_id=701,
        )
        workspace = await self.service.create_personal_workspace(
            owner_user_id=701,
            name="Личный архив",
        )
        settings = await self.workspace_repository.get_settings(workspace.id)
        modules = await self.service.list_modules(
            workspace_id=workspace.id,
            actor_user_id=701,
        )
        self.assertIsNotNone(settings)
        self.assertFalse(settings.public_archive_enabled)
        self.assertTrue(any(item.module_key == "archive" for item in modules))
        self.assertFalse(any(item.module_key == "qwen" for item in modules))

        with self.assertRaises(WorkspaceModuleAccessError):
            await self.service.set_module_enabled(
                workspace_id=workspace.id,
                actor_user_id=701,
                module_key="qwen",
                is_enabled=True,
            )

    async def test_global_creator_can_allow_module_then_owner_enables_it(self) -> None:
        await self.service.grant_creation_access(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            user_id=702,
        )
        workspace = await self.service.create_personal_workspace(
            owner_user_id=702,
            name="Личный архив 2",
        )
        await self.service.set_module_allowed(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            workspace_id=workspace.id,
            module_key="qwen",
            is_allowed=True,
        )
        module = await self.service.set_module_enabled(
            workspace_id=workspace.id,
            actor_user_id=702,
            module_key="qwen",
            is_enabled=True,
        )
        self.assertTrue(module.is_allowed)
        self.assertTrue(module.is_enabled)

    async def test_public_directory_requires_explicit_enable(self) -> None:
        await self.service.grant_creation_access(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            user_id=703,
        )
        workspace = await self.service.create_personal_workspace(
            owner_user_id=703,
            name="Личный архив 3",
        )
        public_before = await self.service.list_public_workspaces()
        self.assertFalse(any(item.id == workspace.id for item in public_before))
        await self.service.set_public_archive_enabled(
            workspace_id=workspace.id,
            actor_user_id=703,
            enabled=True,
        )
        public_after = await self.service.list_public_workspaces()
        self.assertTrue(any(item.id == workspace.id for item in public_after))

    async def test_taxonomy_is_workspace_scoped(self) -> None:
        await self.service.grant_creation_access(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            user_id=704,
        )
        workspace = await self.service.create_personal_workspace(
            owner_user_id=704,
            name="Личный архив 4",
        )
        category = await self.service.upsert_category(
            workspace_id=workspace.id,
            actor_user_id=704,
            key="custom",
            label="Своя категория",
            emoji="🧩",
        )
        universe = await self.service.upsert_universe(
            workspace_id=workspace.id,
            actor_user_id=704,
            key="custom-world",
            label="Своя вселенная",
            emoji="🌌",
            requires_story=True,
        )
        story = await self.service.upsert_story(
            workspace_id=workspace.id,
            actor_user_id=704,
            universe_key=universe.key,
            key=_TEST_KR_STORY_KEY,
            short_label="ЛА",
            title="Личный архив",
        )
        self.assertEqual(workspace.id, category.workspace_id)
        self.assertEqual(workspace.id, universe.workspace_id)
        self.assertEqual(workspace.id, story.workspace_id)


if __name__ == "__main__":
    unittest.main()
