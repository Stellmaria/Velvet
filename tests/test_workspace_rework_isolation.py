from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.database import Database
from velvet_bot.domains.archive import ArchiveRepository
from velvet_bot.domains.media_rework.manual import request_manual_rework
from velvet_bot.domains.media_rework.repository import MediaReworkRepository
from velvet_bot.domains.public_archive.visibility import public_media_visibility_sql
from velvet_bot.media import MediaDescriptor


class WorkspaceReworkIsolationContractTests(unittest.TestCase):
    def test_followup_migration_runs_after_unified_queue_and_uses_composite_key(self) -> None:
        migration = Path(
            "migrations/z002_workspace_media_rework_isolation.sql"
        ).read_text(encoding="utf-8")
        self.assertTrue(Path("migrations/z001_unified_media_rework_queue.sql").exists())
        self.assertIn("PRIMARY KEY (workspace_id, media_id)", migration)
        self.assertIn("FOREIGN KEY (workspace_id, media_id)", migration)
        self.assertIn("ON CONFLICT (workspace_id, media_id)", migration)
        self.assertIn("WHERE workspace_id = 1", migration)

    def test_visibility_and_repository_are_workspace_scoped(self) -> None:
        visibility = public_media_visibility_sql()
        repository = Path(
            "velvet_bot/domains/media_rework/repository.py"
        ).read_text(encoding="utf-8")
        manual = Path(
            "velvet_bot/domains/media_rework/manual.py"
        ).read_text(encoding="utf-8")
        self.assertIn("active_rework.workspace_id", visibility)
        self.assertIn("rework_character.workspace_id", visibility)
        self.assertIn("workspace_id = $1::BIGINT", repository)
        self.assertIn("character.workspace_id = $2::BIGINT", manual)
        self.assertIn("workspace_id=workspace.id", manual.replace(" ", ""))

    def test_personal_router_precedes_generic_owner_controls(self) -> None:
        bundle = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        isolated = "router.include_router(workspace_rework_isolation_router)"
        generic = "router.include_router(workspace_owner_controls_router)"
        self.assertLess(bundle.index(isolated), bundle.index(generic))

        router = Path(
            "velvet_bot/presentation/telegram/routers/workspace_rework_isolation.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "MediaReworkRepository(database, workspace_id=workspace.id)",
            router,
        )
        self.assertIn("workspace_id=workspace.id", router)
        self.assertIn('F.action == "rework"', router)
        self.assertIn('F.action == "public"', router)

    def test_personal_rework_button_explains_start_and_finish(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/workspace_ui_adjustments.py"
        ).read_text(encoding="utf-8")
        self.assertIn("🛠 Доработать / завершить", source)
        self.assertIn("Повторное нажатие завершает заявку", source)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class WorkspaceReworkIsolationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                TRUNCATE media_rework_events,
                         media_rework_items,
                         media_ai_quality_checks,
                         character_media,
                         media_files,
                         characters
                RESTART IDENTITY CASCADE
                """
            )
            await connection.execute("DELETE FROM workspaces WHERE id <> 1")
            self.workspace_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO workspaces (slug, name, is_system)
                    VALUES ('rework-isolation', 'Rework Isolation', FALSE)
                    RETURNING id
                    """
                )
            )

        self.system_character, _ = await self.database.create_character(
            "Shared Rework System",
            created_by=7221553045,
            created_in_chat=7221553045,
            workspace_id=1,
        )
        self.personal_character, _ = await self.database.create_character(
            "Shared Rework Personal",
            created_by=9001,
            created_in_chat=9001,
            workspace_id=self.workspace_id,
        )
        descriptor = MediaDescriptor(
            telegram_file_id="shared-rework-file",
            telegram_file_unique_id="shared-rework-unique",
            original_file_name="shared-rework.png",
            storage_file_name="shared-rework-storage.png",
            media_type="document",
            mime_type="image/png",
            file_size=2048,
        )
        system_saved = await self.database.save_character_media(
            self.system_character,
            descriptor,
            saved_by=7221553045,
            saved_in_chat=7221553045,
            source_chat_id=7221553045,
            source_message_id=101,
            source_thread_id=None,
            command_message_id=100,
        )
        personal_saved = await self.database.save_character_media(
            self.personal_character,
            descriptor,
            saved_by=9001,
            saved_in_chat=9001,
            source_chat_id=9001,
            source_message_id=201,
            source_thread_id=None,
            command_message_id=200,
        )
        self.assertEqual(system_saved.media_id, personal_saved.media_id)
        self.media_id = system_saved.media_id

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_personal_hold_does_not_hide_system_link_or_queue(self) -> None:
        changed = await request_manual_rework(
            self.database,
            media_id=self.media_id,
            user_id=9001,
            workspace_id=self.workspace_id,
            reason="Personal workspace hold",
        )
        self.assertTrue(changed)

        async with self.database.acquire() as connection:
            links = await connection.fetch(
                """
                SELECT character.workspace_id, link.is_public
                FROM character_media AS link
                JOIN characters AS character ON character.id = link.character_id
                WHERE link.media_id = $1::BIGINT
                ORDER BY character.workspace_id
                """,
                self.media_id,
            )
            queues = await connection.fetch(
                """
                SELECT workspace_id, status
                FROM media_rework_items
                WHERE media_id = $1::BIGINT
                ORDER BY workspace_id
                """,
                self.media_id,
            )

        self.assertEqual(
            [(1, True), (self.workspace_id, False)],
            [(int(row["workspace_id"]), bool(row["is_public"])) for row in links],
        )
        self.assertEqual(
            [(self.workspace_id, "needs_fix")],
            [(int(row["workspace_id"]), str(row["status"])) for row in queues],
        )

        system_repository = MediaReworkRepository(self.database, workspace_id=1)
        personal_repository = MediaReworkRepository(
            self.database,
            workspace_id=self.workspace_id,
        )
        self.assertFalse(await system_repository.is_active(self.media_id))
        self.assertTrue(await personal_repository.is_active(self.media_id))

        system_page = await ArchiveRepository(
            self.database,
            workspace_id=1,
        ).get_page(
            character_id=self.system_character.id,
            offset=0,
            public_only=True,
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        personal_page = await ArchiveRepository(
            self.database,
            workspace_id=self.workspace_id,
        ).get_page(
            character_id=self.personal_character.id,
            offset=0,
            public_only=True,
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        self.assertIsNotNone(system_page)
        self.assertIsNotNone(system_page.media)
        self.assertIsNotNone(personal_page)
        self.assertIsNone(personal_page.media)

        self.assertTrue(await personal_repository.accept(self.media_id, 9001))
        personal_after = await ArchiveRepository(
            self.database,
            workspace_id=self.workspace_id,
        ).get_page(
            character_id=self.personal_character.id,
            offset=0,
            public_only=True,
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        self.assertIsNotNone(personal_after)
        self.assertIsNone(personal_after.media)


if __name__ == "__main__":
    unittest.main()
