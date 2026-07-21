from __future__ import annotations

import inspect
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

import asyncpg

from velvet_bot.app.reference_sessions import ReferenceUploadSessions
from velvet_bot.app.references import build_reference_service
from velvet_bot.database import Database
from velvet_bot.domains.references import ReferenceMediaPayload
from velvet_bot.domains.references.comparison_repository import _save_report
from velvet_bot.domains.workspaces.character_management import create_workspace_character
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceReferenceLibraryContractTests(unittest.TestCase):
    def test_upload_session_pins_workspace_and_character(self) -> None:
        sessions = ReferenceUploadSessions()
        session = sessions.start(
            77,
            workspace_id=55,
            character_id=901,
            character_name="Каэль",
        )
        self.assertEqual(55, session.workspace_id)
        self.assertEqual(901, session.character_id)
        self.assertEqual(session, sessions.get(77))

    def test_reference_service_exposes_workspace_boundary(self) -> None:
        service = build_reference_service(SimpleNamespace())
        for method_name in ("add", "delete", "count", "list", "get_page"):
            parameters = inspect.signature(getattr(service, method_name)).parameters
            self.assertIn("workspace_id", parameters)

    def test_personal_router_precedes_legacy_reference_routers(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        personal = source.index("router.include_router(workspace_reference_library_router)")
        comparison = source.index("router.include_router(reference_comparison_router)")
        documents = source.index("router.include_router(reference_documents_router)")
        albums = source.index("router.include_router(reference_albums_router)")
        management = source.index("router.include_router(reference_management_router)")
        catalog = source.index("router.include_router(references_router)")
        self.assertLess(personal, comparison)
        self.assertLess(personal, documents)
        self.assertLess(personal, albums)
        self.assertLess(personal, management)
        self.assertLess(personal, catalog)

    def test_migration_enforces_workspace_composite_links(self) -> None:
        source = (ROOT / "migrations/906_workspace_references.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("FOREIGN KEY (workspace_id, character_id)", source)
        self.assertIn("FOREIGN KEY (workspace_id, reference_id)", source)
        self.assertIn("REFERENCES character_references(workspace_id, id)", source)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceReferenceLibraryTests(unittest.IsolatedAsyncioTestCase):
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
                    reference_comparison_reports,
                    character_references,
                    workspace_character_aliases,
                    workspace_character_story_links,
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
                f"refs-{int(user_id)}",
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
                INSERT INTO workspace_settings (workspace_id, qwen_enabled)
                VALUES ($1::BIGINT, TRUE)
                ON CONFLICT (workspace_id) DO UPDATE
                SET qwen_enabled = TRUE
                """,
                workspace_id,
            )
            for module_key in ("references", "qwen"):
                await connection.execute(
                    """
                    INSERT INTO workspace_modules (
                        workspace_id, module_key, is_allowed, is_enabled
                    )
                    VALUES ($1::BIGINT, $2::VARCHAR, TRUE, TRUE)
                    ON CONFLICT (workspace_id, module_key) DO UPDATE
                    SET is_allowed = TRUE, is_enabled = TRUE
                    """,
                    workspace_id,
                    module_key,
                )
        return SimpleNamespace(id=workspace_id)

    async def test_same_names_and_files_are_isolated_by_workspace(self) -> None:
        first = await self._create_workspace(901, "First References")
        second = await self._create_workspace(902, "Second References")
        first_character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Каэль",
            created_by=901,
            created_in_chat=1901,
        )
        second_character, _ = await create_workspace_character(
            self.database,
            workspace_id=second.id,
            name="Каэль",
            created_by=902,
            created_in_chat=1902,
        )
        service = build_reference_service(self.database)
        first_result = await service.add(
            workspace_id=first.id,
            character_id=first_character.id,
            media=ReferenceMediaPayload("file-first", "same-visible-image"),
            added_by=901,
        )
        second_result = await service.add(
            workspace_id=second.id,
            character_id=second_character.id,
            media=ReferenceMediaPayload("file-second", "same-visible-image"),
            added_by=902,
        )

        first_items = await service.list(
            first_character.id,
            workspace_id=first.id,
        )
        second_items = await service.list(
            second_character.id,
            workspace_id=second.id,
        )
        self.assertEqual([first_result.reference.id], [item.id for item in first_items])
        self.assertEqual([second_result.reference.id], [item.id for item in second_items])
        self.assertEqual([first.id], [item.workspace_id for item in first_items])
        self.assertEqual([second.id], [item.workspace_id for item in second_items])
        self.assertIsNone(
            await service.get_page(
                first_character.id,
                0,
                workspace_id=second.id,
            )
        )

    async def test_foreign_delete_does_not_remove_reference(self) -> None:
        first = await self._create_workspace(903, "Delete First")
        second = await self._create_workspace(904, "Delete Second")
        character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Эрик",
            created_by=903,
            created_in_chat=1903,
        )
        service = build_reference_service(self.database)
        added = await service.add(
            workspace_id=first.id,
            character_id=character.id,
            media=ReferenceMediaPayload("file-eric", "unique-eric"),
            added_by=903,
        )
        foreign = await service.delete(
            workspace_id=second.id,
            character_id=character.id,
            reference_id=added.reference.id,
        )
        self.assertIsNone(foreign.reference)
        self.assertEqual(
            1,
            await service.count(character.id, workspace_id=first.id),
        )

    async def test_comparison_report_rejects_foreign_reference(self) -> None:
        first = await self._create_workspace(905, "Compare First")
        second = await self._create_workspace(906, "Compare Second")
        first_character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Каэль",
            created_by=905,
            created_in_chat=1905,
        )
        second_character, _ = await create_workspace_character(
            self.database,
            workspace_id=second.id,
            name="Рейнольдс",
            created_by=906,
            created_in_chat=1906,
        )
        service = build_reference_service(self.database)
        first_reference = await service.add(
            workspace_id=first.id,
            character_id=first_character.id,
            media=ReferenceMediaPayload("first-ref", "first-ref-unique"),
            added_by=905,
        )
        second_reference = await service.add(
            workspace_id=second.id,
            character_id=second_character.id,
            media=ReferenceMediaPayload("second-ref", "second-ref-unique"),
            added_by=906,
        )
        report = {
            "overall_score": 88,
            "face_score": 90,
            "hair_score": 86,
            "body_score": 80,
            "unique_traits_score": 78,
            "confidence": 84,
            "verdict": "strong",
        }
        valid_id = await _save_report(
            self.database,
            workspace_id=first.id,
            character_id=first_character.id,
            reference_id=first_reference.reference.id,
            result_file_id="result-file",
            result_file_unique_id="result-unique",
            provider="ollama",
            model="qwen",
            report=report,
            created_by=905,
        )
        self.assertGreater(valid_id, 0)

        with self.assertRaises(asyncpg.ForeignKeyViolationError):
            await _save_report(
                self.database,
                workspace_id=first.id,
                character_id=first_character.id,
                reference_id=second_reference.reference.id,
                result_file_id="foreign-result",
                result_file_unique_id="foreign-result-unique",
                provider="ollama",
                model="qwen",
                report=report,
                created_by=905,
            )


if __name__ == "__main__":
    unittest.main()
