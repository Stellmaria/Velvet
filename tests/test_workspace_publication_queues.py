from __future__ import annotations

import inspect
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

import asyncpg

from velvet_bot.database import Database
from velvet_bot.domains.publication.draft_repository import PublicationDraftRepository
from velvet_bot.domains.publication.models import PublicationInboxPayload
from velvet_bot.domains.publication.repository import PublicationRepository
from velvet_bot.domains.publication.validation_repository import (
    PublicationValidationRepository,
)
from velvet_bot.domains.workspaces.character_management import create_workspace_character
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID

ROOT = Path(__file__).resolve().parents[1]


class WorkspacePublicationContractTests(unittest.TestCase):
    def test_migration_adds_strict_workspace_boundaries(self) -> None:
        source = (ROOT / "migrations/907_workspace_publications.sql").read_text(
            encoding="utf-8"
        )
        for table in (
            "publication_inbox_items",
            "publication_drafts",
            "publication_draft_items",
            "publication_events",
        ):
            self.assertIn(f"ALTER TABLE {table}", source)
        self.assertIn("publication_draft_items_workspace_draft_fkey", source)
        self.assertIn("publication_events_workspace_draft_fkey", source)
        self.assertIn(
            "UNIQUE (workspace_id, owner_id, source_chat_id, source_message_id)",
            source,
        )

    def test_publication_apis_accept_workspace_scope(self) -> None:
        for function in (
            PublicationRepository.get_draft,
            PublicationRepository.list_drafts,
            PublicationRepository.claim_for_publishing,
            PublicationDraftRepository.set_spoiler,
            PublicationDraftRepository.update_text,
            PublicationDraftRepository.schedule,
            PublicationDraftRepository.cancel,
        ):
            with self.subTest(function=function.__qualname__):
                self.assertIn("workspace_id", inspect.signature(function).parameters)

    def test_personal_router_precedes_legacy_publication_center(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            source.index("router.include_router(workspace_publications_router)"),
            source.index("router.include_router(publication_center_router)"),
        )

    def test_validation_uses_workspace_aliases_and_universe_rules(self) -> None:
        repository_source = (
            ROOT / "velvet_bot/domains/publication/validation_repository.py"
        ).read_text(encoding="utf-8")
        service_source = (
            ROOT / "velvet_bot/domains/publication/validation_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("workspace_character_aliases", repository_source)
        self.assertIn("workspace_universes", repository_source)
        self.assertIn("requires_story", service_source)
        self.assertNotIn("_STORY_REQUIRED_UNIVERSES", service_source)

    def test_worker_uses_internal_cross_workspace_lookup_only_for_due_queue(self) -> None:
        source = (
            ROOT / "velvet_bot/domains/publication/service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("workspace_id=None", source)
        self.assertIn("resolved_workspace_id = int(draft.workspace_id)", source)

    def test_owner_gate_has_guarded_workspace_routes(self) -> None:
        policy = (ROOT / "velvet_bot/core/access/policy.py").read_text(
            encoding="utf-8"
        )
        middleware = (
            ROOT / "velvet_bot/presentation/telegram/middleware/access.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"pubq:"', policy)
        self.assertIn('"publications"', policy)
        self.assertIn("_has_active_personal_workspace", middleware)
        self.assertIn("is_workspace_member_callback_data", middleware)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspacePublicationTests(unittest.IsolatedAsyncioTestCase):
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
                    publication_events,
                    publication_draft_items,
                    publication_drafts,
                    publication_inbox_items,
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

    async def _create_workspace(
        self,
        *,
        user_id: int,
        name: str,
        chat_id: int,
    ) -> SimpleNamespace:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspaces (slug, name, is_system)
                VALUES ($1::VARCHAR, $2::VARCHAR, FALSE)
                RETURNING id
                """,
                f"pub-{user_id}",
                name,
            )
            assert row is not None
            workspace_id = int(row["id"])
            await connection.execute(
                """
                INSERT INTO workspace_members (workspace_id, user_id, role)
                VALUES ($1::BIGINT, $2::BIGINT, 'owner')
                """,
                workspace_id,
                user_id,
            )
            await connection.execute(
                """
                INSERT INTO workspace_settings (workspace_id, timezone)
                VALUES ($1::BIGINT, 'Europe/Berlin')
                """,
                workspace_id,
            )
            await connection.execute(
                """
                INSERT INTO workspace_modules (
                    workspace_id, module_key, is_allowed, is_enabled
                )
                VALUES ($1::BIGINT, 'publications', TRUE, TRUE)
                """,
                workspace_id,
            )
            await connection.execute(
                """
                INSERT INTO workspace_channels (workspace_id, kind, chat_id)
                VALUES ($1::BIGINT, 'publication', $2::BIGINT)
                """,
                workspace_id,
                chat_id,
            )
        return SimpleNamespace(id=workspace_id, user_id=user_id, chat_id=chat_id)

    async def _insert_draft(
        self,
        workspace: SimpleNamespace,
        *,
        owner_id: int | None = None,
        content_hash: str,
        status: str = "draft",
    ) -> int:
        async with self.database.acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO publication_drafts (
                    workspace_id, owner_id, target_chat_id,
                    text_content, status, content_hash
                )
                VALUES (
                    $1::BIGINT, $2::BIGINT, $3::BIGINT,
                    'test publication', $4::VARCHAR, $5::CHAR(64)
                )
                RETURNING id
                """,
                workspace.id,
                owner_id if owner_id is not None else workspace.user_id,
                workspace.chat_id,
                status,
                content_hash,
            )
        return int(value)

    async def test_same_source_message_isolated_between_workspaces(self) -> None:
        first = await self._create_workspace(
            user_id=1101,
            name="First Publications",
            chat_id=-100700001,
        )
        second = await self._create_workspace(
            user_id=1102,
            name="Second Publications",
            chat_id=-100700002,
        )
        repository = PublicationDraftRepository(self.database)
        for workspace in (first, second):
            await repository.capture_inbox(
                PublicationInboxPayload(
                    owner_id=9999,
                    source_chat_id=500,
                    source_message_id=600,
                    media_group_id=None,
                    text_content="same source",
                    telegram_file_id=None,
                    telegram_file_unique_id=None,
                    media_type="text",
                    mime_type=None,
                    file_name=None,
                    file_size=None,
                    has_spoiler=False,
                    workspace_id=workspace.id,
                )
            )
        async with self.database.acquire() as connection:
            count = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM publication_inbox_items
                WHERE owner_id = 9999
                  AND source_chat_id = 500
                  AND source_message_id = 600
                """
            )
        self.assertEqual(2, int(count))

    async def test_foreign_workspace_cannot_read_or_mutate_draft(self) -> None:
        first = await self._create_workspace(
            user_id=1201,
            name="First Queue",
            chat_id=-100710001,
        )
        second = await self._create_workspace(
            user_id=1202,
            name="Second Queue",
            chat_id=-100710002,
        )
        draft_id = await self._insert_draft(first, content_hash="a" * 64)
        repository = PublicationRepository(self.database)
        self.assertIsNotNone(
            await repository.get_draft(
                draft_id,
                owner_id=first.user_id,
                workspace_id=first.id,
            )
        )
        self.assertIsNone(
            await repository.get_draft(
                draft_id,
                owner_id=second.user_id,
                workspace_id=second.id,
            )
        )
        with self.assertRaises(ValueError):
            await PublicationDraftRepository(self.database).cancel(
                draft_id,
                owner_id=second.user_id,
                workspace_id=second.id,
            )

    async def test_team_list_is_workspace_scoped_not_creator_scoped(self) -> None:
        workspace = await self._create_workspace(
            user_id=1301,
            name="Team Queue",
            chat_id=-100720001,
        )
        first_id = await self._insert_draft(
            workspace,
            owner_id=1301,
            content_hash="b" * 64,
        )
        second_id = await self._insert_draft(
            workspace,
            owner_id=1302,
            content_hash="c" * 64,
        )
        page = await PublicationRepository(self.database).list_drafts(
            owner_id=1301,
            statuses=("draft",),
            workspace_id=workspace.id,
        )
        self.assertEqual({first_id, second_id}, {item.id for item in page.items})

    async def test_duplicate_draft_does_not_cross_workspace(self) -> None:
        first = await self._create_workspace(
            user_id=1401,
            name="Duplicate First",
            chat_id=-100730001,
        )
        second = await self._create_workspace(
            user_id=1402,
            name="Duplicate Second",
            chat_id=-100730002,
        )
        await self._insert_draft(
            first,
            content_hash="d" * 64,
            status="scheduled",
        )
        second_id = await self._insert_draft(
            second,
            content_hash="d" * 64,
        )
        draft = await PublicationRepository(self.database).get_draft(
            second_id,
            owner_id=second.user_id,
            workspace_id=second.id,
        )
        assert draft is not None
        context = await PublicationValidationRepository(self.database).load_context(
            draft,
            normalized_aliases=[],
            text="",
        )
        self.assertIsNone(context.duplicate_draft)

    async def test_character_alias_resolution_stays_in_workspace(self) -> None:
        first = await self._create_workspace(
            user_id=1501,
            name="Characters First",
            chat_id=-100740001,
        )
        second = await self._create_workspace(
            user_id=1502,
            name="Characters Second",
            chat_id=-100740002,
        )
        first_character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Каэль",
            created_by=first.user_id,
            created_in_chat=1,
        )
        second_character, _ = await create_workspace_character(
            self.database,
            workspace_id=second.id,
            name="Каэль",
            created_by=second.user_id,
            created_in_chat=2,
        )
        draft_id = await self._insert_draft(first, content_hash="e" * 64)
        draft = await PublicationRepository(self.database).get_draft(
            draft_id,
            owner_id=first.user_id,
            workspace_id=first.id,
        )
        assert draft is not None
        context = await PublicationValidationRepository(self.database).load_context(
            draft,
            normalized_aliases=["каэль"],
            text="",
        )
        self.assertEqual([first_character.id], [item.id for item in context.characters])
        self.assertNotIn(second_character.id, [item.id for item in context.characters])

    async def test_composite_fk_blocks_foreign_event_and_worker_can_load_due(self) -> None:
        first = await self._create_workspace(
            user_id=1601,
            name="Due First",
            chat_id=-100750001,
        )
        second = await self._create_workspace(
            user_id=1602,
            name="Due Second",
            chat_id=-100750002,
        )
        draft_id = await self._insert_draft(
            first,
            content_hash="f" * 64,
            status="scheduled",
        )
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                UPDATE publication_drafts
                SET scheduled_at = NOW() - INTERVAL '1 minute'
                WHERE id = $1::BIGINT
                """,
                draft_id,
            )
            with self.assertRaises(asyncpg.ForeignKeyViolationError):
                await connection.execute(
                    """
                    INSERT INTO publication_events (
                        workspace_id, draft_id, event_type
                    )
                    VALUES ($1::BIGINT, $2::BIGINT, 'forged')
                    """,
                    second.id,
                    draft_id,
                )
        repository = PublicationRepository(self.database)
        self.assertIn(draft_id, await repository.list_due_draft_ids(limit=5))
        internal = await repository.get_draft(
            draft_id,
            owner_id=None,
            workspace_id=None,
        )
        self.assertIsNotNone(internal)
        assert internal is not None
        self.assertEqual(first.id, internal.workspace_id)
        self.assertEqual(first.chat_id, internal.target_chat_id)


if __name__ == "__main__":
    unittest.main()
