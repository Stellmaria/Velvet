from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.app.public_archive import build_public_archive_service
from velvet_bot.database import Database
from velvet_bot.domains.archive.repository import ArchiveRepository
from velvet_bot.domains.characters.repository import CharacterDirectoryRepository
from velvet_bot.domains.public_archive.repository import PublicArchiveRepository
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.media import MediaDescriptor

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceArchiveIsolationContractTests(unittest.TestCase):
    def test_active_workspace_migration_is_present(self) -> None:
        sql = (ROOT / "migrations/902_workspace_active_selection.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS user_workspace_preferences", sql)
        self.assertIn("active_workspace_id", sql)

    def test_archive_repositories_have_workspace_guards(self) -> None:
        archive_source = (ROOT / "velvet_bot/domains/archive/repository.py").read_text(
            encoding="utf-8"
        )
        public_source = (
            ROOT / "velvet_bot/domains/public_archive/repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("c.workspace_id = $3::BIGINT", archive_source)
        self.assertIn("c.workspace_id = $4::BIGINT", public_source)
        self.assertIn("_media_belongs_to_workspace", public_source)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceArchiveIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        await self._reset()
        self.workspaces = WorkspaceRepository(self.database)
        self.workspace_service = WorkspaceService(self.workspaces)

    async def asyncTearDown(self) -> None:
        await self._reset()
        await self.database.close()

    async def _reset(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute("TRUNCATE characters RESTART IDENTITY CASCADE")
            await connection.execute("DELETE FROM user_workspace_preferences")
            await connection.execute(
                "DELETE FROM workspace_members WHERE workspace_id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute(
                "DELETE FROM workspace_channels WHERE workspace_id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute(
                "DELETE FROM workspaces WHERE id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )

    async def _create_workspace_with_character(
        self,
        *,
        owner_user_id: int,
        slug: str,
        character_name: str,
    ):
        workspace = await self.workspace_service.create_personal_workspace(
            name=slug.replace("-", " ").title(),
            slug=slug,
            owner_user_id=owner_user_id,
        )
        character, _ = await self.database.create_character(
            character_name,
            created_by=owner_user_id,
            created_in_chat=-100000 - owner_user_id,
            workspace_id=workspace.id,
        )
        return workspace, character

    async def _save_media(self, character, *, suffix: str):
        return await self.database.save_character_media(
            character,
            MediaDescriptor(
                telegram_file_id=f"file-{suffix}",
                telegram_file_unique_id=f"unique-{suffix}",
                original_file_name=f"{suffix}.png",
                storage_file_name=f"{suffix}__hash.png",
                media_type="document",
                mime_type="image/png",
                file_size=128,
            ),
            saved_by=character.created_by,
            saved_in_chat=character.created_in_chat or -1,
            source_chat_id=character.created_in_chat or -1,
            source_message_id=10,
            source_thread_id=None,
            command_message_id=11,
        )

    async def test_active_workspace_cannot_be_switched_to_foreign_workspace(self) -> None:
        first, _ = await self._create_workspace_with_character(
            owner_user_id=101,
            slug="owner-one",
            character_name="Каин",
        )
        second, _ = await self._create_workspace_with_character(
            owner_user_id=202,
            slug="owner-two",
            character_name="Аид",
        )

        active = await self.workspace_service.resolve_active_workspace(user_id=101)
        self.assertEqual(first.id, active.id)
        with self.assertRaises(WorkspaceAccessError):
            await self.workspace_service.set_active_workspace(
                workspace_id=second.id,
                user_id=101,
            )
        active_after = await self.workspace_service.resolve_active_workspace(user_id=101)
        self.assertEqual(first.id, active_after.id)

    async def test_same_telegram_chat_cannot_cross_workspaces(self) -> None:
        first, _ = await self._create_workspace_with_character(
            owner_user_id=101,
            slug="channel-one",
            character_name="Каин",
        )
        second, _ = await self._create_workspace_with_character(
            owner_user_id=202,
            slug="channel-two",
            character_name="Аид",
        )
        await self.workspace_service.configure_channel(
            workspace_id=first.id,
            actor_user_id=101,
            kind="archive",
            chat_id=-100777,
            url="https://t.me/archive_one",
        )
        with self.assertRaises(ValueError):
            await self.workspace_service.configure_channel(
                workspace_id=second.id,
                actor_user_id=202,
                kind="archive",
                chat_id=-100777,
                url="https://t.me/archive_two",
            )

    async def test_private_archive_rejects_foreign_character_and_mutation(self) -> None:
        first, character = await self._create_workspace_with_character(
            owner_user_id=101,
            slug="archive-one",
            character_name="Каин",
        )
        second, _ = await self._create_workspace_with_character(
            owner_user_id=202,
            slug="archive-two",
            character_name="Аид",
        )
        saved = await self._save_media(character, suffix="foreign-private")

        own_repository = ArchiveRepository(self.database, workspace_id=first.id)
        foreign_repository = ArchiveRepository(self.database, workspace_id=second.id)
        self.assertIsNotNone(
            await own_repository.get_page(character_id=character.id, offset=0)
        )
        self.assertIsNone(
            await foreign_repository.get_page(character_id=character.id, offset=0)
        )
        self.assertIsNone(
            await foreign_repository.toggle_public_visibility(
                character_id=character.id,
                media_id=saved.media_id,
            )
        )

    async def test_public_activity_cannot_be_written_to_foreign_workspace(self) -> None:
        first, character = await self._create_workspace_with_character(
            owner_user_id=101,
            slug="public-one",
            character_name="Каин",
        )
        second, _ = await self._create_workspace_with_character(
            owner_user_id=202,
            slug="public-two",
            character_name="Аид",
        )
        saved = await self._save_media(character, suffix="foreign-public")

        own_repository = PublicArchiveRepository(self.database, workspace_id=first.id)
        foreign_repository = PublicArchiveRepository(self.database, workspace_id=second.id)
        await own_repository.record_view(
            character_id=character.id,
            media_id=saved.media_id,
            user_id=501,
        )
        await foreign_repository.record_view(
            character_id=character.id,
            media_id=saved.media_id,
            user_id=502,
        )
        state = await foreign_repository.get_media_state(
            character_id=character.id,
            media_id=saved.media_id,
            user_id=502,
        )
        self.assertEqual(0, state.view_count)
        async with self.database.acquire() as connection:
            foreign_count = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM public_media_view_stats
                WHERE character_id = $1::BIGINT
                  AND media_id = $2::BIGINT
                  AND user_id = 502
                """,
                character.id,
                saved.media_id,
            )
        self.assertEqual(0, int(foreign_count or 0))

    async def test_public_directory_lists_only_selected_workspace(self) -> None:
        first, first_character = await self._create_workspace_with_character(
            owner_user_id=101,
            slug="directory-one",
            character_name="Каин",
        )
        second, second_character = await self._create_workspace_with_character(
            owner_user_id=202,
            slug="directory-two",
            character_name="Аид",
        )
        first_media = await self._save_media(first_character, suffix="directory-first")
        second_media = await self._save_media(second_character, suffix="directory-second")
        first_directory = CharacterDirectoryRepository(
            self.database,
            workspace_id=first.id,
        )
        second_directory = CharacterDirectoryRepository(
            self.database,
            workspace_id=second.id,
        )
        await first_directory.set_category(character_id=first_character.id, category="male")
        await first_directory.set_universe(character_id=first_character.id, universe="original")
        await second_directory.set_category(character_id=second_character.id, category="male")
        await second_directory.set_universe(character_id=second_character.id, universe="original")
        await ArchiveRepository(
            self.database,
            workspace_id=first.id,
        ).toggle_public_visibility(
            character_id=first_character.id,
            media_id=first_media.media_id,
        )
        await ArchiveRepository(
            self.database,
            workspace_id=second.id,
        ).toggle_public_visibility(
            character_id=second_character.id,
            media_id=second_media.media_id,
        )

        service = build_public_archive_service(self.database, workspace_id=first.id)
        page = await service.list_characters(
            category="male",
            universe="original",
        )
        self.assertEqual([first_character.id], [item.character.id for item in page.items])


if __name__ == "__main__":
    unittest.main()
