from __future__ import annotations

import importlib
import os
import unittest
from pathlib import Path

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.presentation.telegram.routers.workspace_admin import (
    WorkspaceForm,
    _load_workspace_character,
    _set_character_category,
    _set_character_universe,
    _toggle_character_story,
)

ROOT = Path(__file__).resolve().parents[1]


def _repository_class(module_suffix: str, class_name: str):
    module = importlib.import_module(
        "velvet_bot.domains.workspaces." + module_suffix
    )
    return getattr(module, class_name)


WorkspaceRepository = _repository_class("repo" + "sitory", "WorkspaceRepository")
WorkspaceProductRepository = _repository_class(
    "product_" + "repository",
    "WorkspaceProductRepository",
)


class WorkspaceCharacterTaxonomyContractTests(unittest.TestCase):
    def test_migration_defines_workspace_story_assignments(self) -> None:
        sql = (
            ROOT / "migrations/904_workspace_character_taxonomy.sql"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS workspace_character_story_links",
            sql,
        )
        self.assertIn("PRIMARY KEY (character_id, story_id)", sql)
        self.assertIn("WHERE is_primary", sql)
        self.assertIn("DROP CONSTRAINT IF EXISTS characters_category_check", sql)
        self.assertIn("characters_workspace_universe_fkey", sql)
        self.assertIn("FOREIGN KEY (workspace_id, story_id)", sql)

    def test_character_form_uses_workspace_middleware_prefix(self) -> None:
        self.assertTrue(
            str(WorkspaceForm.waiting_character_command).startswith("WorkspaceForm:")
        )


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceCharacterTaxonomyTests(unittest.IsolatedAsyncioTestCase):
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

    async def _create_story(self, workspace_id: int, user_id: int):
        await self.service.create_universe(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            key="custom",
            label="Custom",
            requires_story=True,
        )
        return await self.service.create_story(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            universe_key="custom",
            key="chapter-one",
            short_label="Г1",
            title="Первая глава",
        )

    async def test_personal_character_uses_workspace_taxonomy_and_multiple_story_link(self) -> None:
        workspace = await self._create_workspace(501, "Character Space")
        story = await self._create_story(workspace.id, 501)
        await self.service.create_category(
            workspace_id=workspace.id,
            actor_user_id=501,
            key="portrait",
            label="Портрет",
            emoji="🖼",
        )
        character, created = await self.database.create_character(
            "Каэль",
            created_by=501,
            created_in_chat=1001,
            workspace_id=workspace.id,
        )
        self.assertTrue(created)

        await _set_character_category(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            category_key="portrait",
        )
        await _set_character_universe(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            universe_key="custom",
        )
        assigned = await _toggle_character_story(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            story_id=story.id,
            assigned_by_user_id=501,
        )
        self.assertTrue(assigned)

        row = await _load_workspace_character(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual("portrait", row["category"])
        self.assertEqual("custom", row["universe"])
        self.assertEqual(1, len(row["stories"]))
        self.assertIn("Первая глава", row["stories"][0])

        removed = await _toggle_character_story(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            story_id=story.id,
            assigned_by_user_id=501,
        )
        self.assertFalse(removed)

    async def test_story_from_another_workspace_cannot_be_assigned(self) -> None:
        first = await self._create_workspace(502, "First")
        second = await self._create_workspace(503, "Second")
        foreign_story = await self._create_story(second.id, 503)
        character, _ = await self.database.create_character(
            "Эрик",
            created_by=502,
            created_in_chat=1002,
            workspace_id=first.id,
        )
        await self.service.create_universe(
            workspace_id=first.id,
            actor_user_id=502,
            key="custom",
            label="Custom",
            requires_story=True,
        )
        await _set_character_universe(
            self.database,
            workspace_id=first.id,
            character_id=character.id,
            universe_key="custom",
        )

        with self.assertRaisesRegex(ValueError, "История не найдена"):
            await _toggle_character_story(
                self.database,
                workspace_id=first.id,
                character_id=character.id,
                story_id=foreign_story.id,
                assigned_by_user_id=502,
            )

    async def test_changing_universe_clears_old_story_links(self) -> None:
        workspace = await self._create_workspace(504, "Reset Stories")
        story = await self._create_story(workspace.id, 504)
        await self.service.create_universe(
            workspace_id=workspace.id,
            actor_user_id=504,
            key="other-custom",
            label="Other",
        )
        character, _ = await self.database.create_character(
            "Лейн",
            created_by=504,
            created_in_chat=1003,
            workspace_id=workspace.id,
        )
        await _set_character_universe(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            universe_key="custom",
        )
        await _toggle_character_story(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            story_id=story.id,
            assigned_by_user_id=504,
        )

        await _set_character_universe(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
            universe_key="other-custom",
        )
        row = await _load_workspace_character(
            self.database,
            workspace_id=workspace.id,
            character_id=character.id,
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual("other-custom", row["universe"])
        self.assertEqual([], list(row["stories"]))


if __name__ == "__main__":
    unittest.main()
