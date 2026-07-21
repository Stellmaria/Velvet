from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
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
        self.assertEqual(10, len(MODULE_HELP))
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
            await connection.execute(
                """
                UPDATE workspace_settings
                SET public_archive_enabled = TRUE,
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                """,
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute(
                """
                UPDATE workspace_modules
                SET is_allowed = TRUE,
                    is_enabled = TRUE,
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                """,
                DEFAULT_WORKSPACE_ID,
            )

    async def _grant_and_create(self, user_id: int, name: str):
        await self.service.grant_creation_access(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            user_id=user_id,
        )
        return await self.service.create_personal_workspace(
            owner_user_id=user_id,
            name=name,
        )

    async def test_only_stell_can_grant_workspace_creation(self) -> None:
        with self.assertRaises(WorkspaceCreationAccessError):
            await self.service.grant_creation_access(
                actor_user_id=999,
                user_id=101,
            )

    async def test_user_without_grant_cannot_create_workspace(self) -> None:
        with self.assertRaises(WorkspaceCreationAccessError):
            await self.service.create_personal_workspace(
                owner_user_id=101,
                name="Denied Archive",
            )

    async def test_granted_workspace_is_private_and_modules_are_initialized(self) -> None:
        workspace = await self._grant_and_create(101, "Private Archive")
        settings = await self.workspace_repository.get_settings(workspace.id)
        modules = await self.product_repository.list_modules(workspace.id)

        self.assertIsNotNone(settings)
        assert settings is not None
        self.assertFalse(settings.public_archive_enabled)
        self.assertTrue(modules)
        self.assertTrue(
            all(item.is_enabled for item in modules if item.is_allowed)
        )
        self.assertFalse(await self.service.can_create_workspace(101))

    async def test_system_velvet_is_public_by_default(self) -> None:
        public = await self.service.list_public_workspaces()
        self.assertIn(DEFAULT_WORKSPACE_ID, {item.id for item in public})

    async def test_private_workspace_appears_only_after_owner_enables_public_mode(self) -> None:
        workspace = await self._grant_and_create(102, "Publish Later")
        before = {item.id for item in await self.service.list_public_workspaces()}
        self.assertNotIn(workspace.id, before)

        await self.service.set_public_archive_enabled(
            workspace_id=workspace.id,
            actor_user_id=102,
            enabled=True,
        )
        after = {item.id for item in await self.service.list_public_workspaces()}
        self.assertIn(workspace.id, after)

    async def test_owner_cannot_enable_module_forbidden_by_stell(self) -> None:
        workspace = await self._grant_and_create(103, "Restricted Modules")
        await self.service.set_module_allowed(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            workspace_id=workspace.id,
            module_key="qwen",
            is_allowed=False,
        )
        with self.assertRaises(WorkspaceModuleAccessError):
            await self.service.set_module_enabled(
                workspace_id=workspace.id,
                actor_user_id=103,
                module_key="qwen",
                is_enabled=True,
            )

    async def test_module_keyboard_has_help_button_for_every_module(self) -> None:
        workspace = await self._grant_and_create(104, "Module Help")
        modules = await self.product_repository.list_modules(workspace.id)
        markup = build_modules_keyboard(workspace.id, modules)
        self.assertEqual(len(modules) + 1, len(markup.inline_keyboard))
        self.assertTrue(all(len(row) == 2 for row in markup.inline_keyboard[:-1]))

    async def test_same_custom_taxonomy_keys_are_isolated(self) -> None:
        first = await self._grant_and_create(105, "First Taxonomy")
        second = await self._grant_and_create(106, "Second Taxonomy")

        for workspace, user_id, label in (
            (first, 105, "Первая"),
            (second, 106, "Вторая"),
        ):
            category = await self.service.create_category(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                key="solo",
                label=label,
            )
            universe = await self.service.create_universe(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                key="custom",
                label=label,
                requires_story=True,
            )
            story = await self.service.create_story(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                universe_key="custom",
                key="chapter-one",
                short_label="Г1",
                title=label,
            )
            self.assertEqual(workspace.id, category.workspace_id)
            self.assertEqual(workspace.id, universe.workspace_id)
            self.assertEqual(workspace.id, story.workspace_id)

        first_categories = await self.service.list_categories(first.id)
        second_categories = await self.service.list_categories(second.id)
        self.assertEqual(
            "Первая",
            next(item.label for item in first_categories if item.key == "solo"),
        )
        self.assertEqual(
            "Вторая",
            next(item.label for item in second_categories if item.key == "solo"),
        )

    async def test_kr_template_is_copied_without_mutating_system_catalog(self) -> None:
        workspace = await self._grant_and_create(107, "KR Template")
        system_before = await self.service.list_stories(
            workspace_id=DEFAULT_WORKSPACE_ID,
            universe_key="kr",
        )
        _, copied = await self.service.import_kr_template(
            workspace_id=workspace.id,
            actor_user_id=107,
        )
        personal = await self.service.list_stories(
            workspace_id=workspace.id,
            universe_key="kr",
        )
        system_after = await self.service.list_stories(
            workspace_id=DEFAULT_WORKSPACE_ID,
            universe_key="kr",
        )

        self.assertGreater(copied, 0)
        self.assertEqual(copied, len(personal))
        self.assertEqual(len(system_before), len(system_after))

    async def test_viewer_cannot_select_private_workspace_as_public(self) -> None:
        workspace = await self._grant_and_create(108, "Still Private")
        selected = await self.service.select_public_workspace(
            user_id=500,
            workspace_id=workspace.id,
        )
        self.assertFalse(selected)
        self.assertEqual(
            DEFAULT_WORKSPACE_ID,
            await self.service.public_workspace_id_for_user(500),
        )


if __name__ == "__main__":
    unittest.main()
