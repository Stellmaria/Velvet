from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.database import Database
from velvet_bot.domains.characters.repository import CharacterDirectoryRepository
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, Workspace, WorkspaceMembership
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.domains.workspaces.service import (
    WorkspaceAccessError,
    WorkspaceService,
    normalize_workspace_name,
    normalize_workspace_slug,
    validate_workspace_url,
)

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceFoundationContractTests(unittest.IsolatedAsyncioTestCase):
    def test_migration_creates_tenant_boundary(self) -> None:
        sql = (ROOT / "migrations/901_workspaces.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS workspaces", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_members", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_settings", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_channels", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS workspace_id BIGINT", sql)
        self.assertIn("UPDATE characters\nSET workspace_id = 1", sql)
        self.assertIn("uq_characters_workspace_normalized_name", sql)
        self.assertNotIn("UNIQUE (normalized_name)", sql)

    def test_workspace_input_normalization(self) -> None:
        self.assertEqual("Архив Виктории", normalize_workspace_name("  Архив   Виктории "))
        self.assertEqual("victoria-archive", normalize_workspace_slug("Victoria Archive"))
        self.assertEqual(
            "https://t.me/c/123/456",
            validate_workspace_url(" https://t.me/c/123/456 "),
        )
        with self.assertRaises(ValueError):
            validate_workspace_url("https://example.com/archive")

    async def test_foreign_workspace_is_denied(self) -> None:
        now = datetime.now(UTC)
        repository = SimpleNamespace(
            get_membership=AsyncMock(return_value=None),
            get=AsyncMock(
                return_value=Workspace(
                    id=17,
                    slug="other",
                    name="Other",
                    is_system=False,
                    created_at=now,
                    updated_at=now,
                )
            ),
        )
        service = WorkspaceService(repository)

        with self.assertRaises(WorkspaceAccessError):
            await service.require_role(workspace_id=17, user_id=91)

    async def test_global_owner_support_access_is_explicit(self) -> None:
        now = datetime.now(UTC)
        repository = SimpleNamespace(
            get_membership=AsyncMock(return_value=None),
            get=AsyncMock(
                return_value=Workspace(
                    id=17,
                    slug="other",
                    name="Other",
                    is_system=False,
                    created_at=now,
                    updated_at=now,
                )
            ),
        )
        service = WorkspaceService(repository)

        membership = await service.require_role(
            workspace_id=17,
            user_id=7221553045,
            minimum_role="owner",
            global_owner=True,
        )

        self.assertEqual("owner", membership.role)
        self.assertEqual(17, membership.workspace_id)

    async def test_editor_cannot_change_workspace_settings(self) -> None:
        now = datetime.now(UTC)
        repository = SimpleNamespace(
            get_membership=AsyncMock(
                return_value=WorkspaceMembership(
                    workspace_id=17,
                    user_id=91,
                    role="editor",
                    created_at=now,
                    updated_at=now,
                )
            ),
            update_settings=AsyncMock(),
        )
        service = WorkspaceService(repository)

        with self.assertRaises(WorkspaceAccessError):
            await service.update_settings(
                workspace_id=17,
                actor_user_id=91,
                timezone="Europe/Warsaw",
                public_archive_enabled=True,
                downloads_mode="watermark",
                qwen_enabled=False,
            )
        repository.update_settings.assert_not_awaited()


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                "TRUNCATE character_media, media_files, characters RESTART IDENTITY CASCADE"
            )
            await connection.execute("DELETE FROM workspaces WHERE id <> $1", DEFAULT_WORKSPACE_ID)
        self.repository = WorkspaceRepository(self.database)
        self.service = WorkspaceService(self.repository)

    async def asyncTearDown(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                "TRUNCATE character_media, media_files, characters RESTART IDENTITY CASCADE"
            )
            await connection.execute("DELETE FROM workspaces WHERE id <> $1", DEFAULT_WORKSPACE_ID)
        await self.database.close()

    async def test_same_character_name_is_isolated_between_workspaces(self) -> None:
        first_workspace = await self.service.create_personal_workspace(
            name="Archive One",
            slug="archive-one",
            owner_user_id=101,
        )
        second_workspace = await self.service.create_personal_workspace(
            name="Archive Two",
            slug="archive-two",
            owner_user_id=202,
        )

        first, first_created = await self.database.create_character(
            "Каин",
            created_by=101,
            created_in_chat=-1001,
            workspace_id=first_workspace.id,
        )
        second, second_created = await self.database.create_character(
            "КАИН",
            created_by=202,
            created_in_chat=-2002,
            workspace_id=second_workspace.id,
        )

        self.assertTrue(first_created)
        self.assertTrue(second_created)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first_workspace.id, first.workspace_id)
        self.assertEqual(second_workspace.id, second.workspace_id)
        self.assertEqual(
            first.id,
            (
                await self.database.get_character(
                    "Каин",
                    workspace_id=first_workspace.id,
                )
            ).id,
        )
        self.assertEqual(
            second.id,
            (
                await self.database.get_character(
                    "Каин",
                    workspace_id=second_workspace.id,
                )
            ).id,
        )
        self.assertIsNone(await self.database.get_character("Каин"))

    async def test_character_directory_cannot_open_foreign_character(self) -> None:
        first_workspace = await self.service.create_personal_workspace(
            name="Archive One",
            slug="directory-one",
            owner_user_id=101,
        )
        second_workspace = await self.service.create_personal_workspace(
            name="Archive Two",
            slug="directory-two",
            owner_user_id=202,
        )
        first, _ = await self.database.create_character(
            "Аид",
            created_by=101,
            created_in_chat=-1001,
            workspace_id=first_workspace.id,
        )
        second, _ = await self.database.create_character(
            "Тесса",
            created_by=202,
            created_in_chat=-2002,
            workspace_id=second_workspace.id,
        )

        directory = CharacterDirectoryRepository(
            self.database,
            workspace_id=first_workspace.id,
        )

        self.assertIsNotNone(await directory.get_item(first.id))
        self.assertIsNone(await directory.get_item(second.id))


if __name__ == "__main__":
    unittest.main()
