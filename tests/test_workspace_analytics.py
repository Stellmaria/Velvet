from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import asyncpg

from velvet_bot.channel_analytics import ParsedChannelPost, PromptSignals
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.analytics_access import (
    resolve_analytics_ingest_workspace,
    resolve_analytics_workspace_context,
)
from velvet_bot.domains.workspaces.analytics_ingest import ingest_workspace_channel_post
from velvet_bot.domains.workspaces.character_management import create_workspace_character
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.domains.workspaces.service import WorkspaceService

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceAnalyticsContractTests(unittest.TestCase):
    def test_migration_enforces_one_workspace_per_telegram_chat(self) -> None:
        source = (
            ROOT / "migrations/908_workspace_channel_ownership.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("enforce_workspace_channel_owner", source)
        self.assertIn("pg_advisory_xact_lock(NEW.chat_id)", source)
        self.assertIn("workspace_id <> NEW.workspace_id", source)
        self.assertIn("ERRCODE = '23505'", source)

    def test_personal_router_precedes_all_legacy_analytics(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/analytics.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            source.index("router.include_router(workspace_analytics_router)"),
            source.index("router.include_router(channel_analytics_router)"),
        )
        self.assertLess(
            source.index("router.include_router(workspace_analytics_router)"),
            source.index("router.include_router(analytics_management_router)"),
        )

    def test_owner_gate_opens_dashboard_but_not_global_management(self) -> None:
        source = (ROOT / "velvet_bot/core/access/policy.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"analytics"', source)
        self.assertIn('"discussionstats"', source)
        self.assertIn('"trackdiscussion"', source)
        self.assertIn('"dash:"', source)
        self.assertNotIn('"dashm:"', source)

    def test_personal_ingest_uses_workspace_alias_catalog(self) -> None:
        source = (
            ROOT / "velvet_bot/domains/workspaces/analytics_ingest.py"
        ).read_text(encoding="utf-8")
        self.assertIn("workspace_character_aliases", source)
        self.assertIn("alias.workspace_id = $1::BIGINT", source)
        self.assertNotIn("SELECT id, name, normalized_name FROM characters", source)

    def test_character_dashboard_reads_workspace_primary_story(self) -> None:
        source = (ROOT / "velvet_bot/analytics_dashboard.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("workspace_character_story_links", source)
        self.assertIn("workspace_stories", source)
        self.assertIn("COALESCE(ws.short_label, s.short_label)", source)

    def test_callback_rechecks_discussion_ownership(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/workspace_analytics.py"
        ).read_text(encoding="utf-8")
        self.assertIn("workspace_owns_discussion_chat", source)
        self.assertIn('callback_data.action in {"discussion", "participants"}', source)
        self.assertIn('PersonalAnalyticsWorkspaceFilter("editor")', source)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceAnalyticsTests(unittest.IsolatedAsyncioTestCase):
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
                    channel_post_links,
                    channel_post_hashtags,
                    channel_posts,
                    telegram_export_imports,
                    workspace_character_aliases,
                    workspace_character_story_links,
                    characters
                RESTART IDENTITY CASCADE
                """
            )
            await connection.execute(
                "DELETE FROM tracked_channels"
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
        role: str = "owner",
        analytics_enabled: bool = True,
    ) -> SimpleNamespace:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspaces (slug, name, is_system)
                VALUES ($1::VARCHAR, $2::VARCHAR, FALSE)
                RETURNING id
                """,
                f"analytics-{user_id}",
                name,
            )
            assert row is not None
            workspace_id = int(row["id"])
            await connection.execute(
                """
                INSERT INTO workspace_members (workspace_id, user_id, role)
                VALUES ($1::BIGINT, $2::BIGINT, $3::VARCHAR)
                """,
                workspace_id,
                user_id,
                role,
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
                VALUES ($1::BIGINT, 'analytics', TRUE, $2::BOOLEAN)
                """,
                workspace_id,
                analytics_enabled,
            )
            await connection.execute(
                """
                INSERT INTO user_workspace_preferences (user_id, workspace_id)
                VALUES ($1::BIGINT, $2::BIGINT)
                """,
                user_id,
                workspace_id,
            )
        return SimpleNamespace(id=workspace_id, user_id=user_id)

    async def test_same_chat_can_have_multiple_kinds_only_inside_one_workspace(self) -> None:
        first = await self._create_workspace(user_id=2101, name="First")
        second = await self._create_workspace(user_id=2102, name="Second")
        repository = WorkspaceRepository(self.database)
        await repository.upsert_channel(
            workspace_id=first.id,
            kind="analytics",
            chat_id=-100810001,
        )
        await repository.upsert_channel(
            workspace_id=first.id,
            kind="publication",
            chat_id=-100810001,
        )
        with self.assertRaises(asyncpg.UniqueViolationError):
            await repository.upsert_channel(
                workspace_id=second.id,
                kind="analytics",
                chat_id=-100810001,
            )

    async def test_context_prioritizes_analytics_and_scopes_discussions(self) -> None:
        workspace = await self._create_workspace(
            user_id=2201,
            name="Dashboard",
            role="reviewer",
        )
        repository = WorkspaceRepository(self.database)
        await repository.upsert_channel(
            workspace_id=workspace.id,
            kind="publication",
            chat_id=-100820002,
        )
        await repository.upsert_channel(
            workspace_id=workspace.id,
            kind="analytics",
            chat_id=-100820001,
        )
        await repository.upsert_channel(
            workspace_id=workspace.id,
            kind="discussion",
            chat_id=-100820003,
        )
        context = await resolve_analytics_workspace_context(
            self.database,
            WorkspaceService(repository),
            user_id=workspace.user_id,
            minimum_role="reviewer",
            system_channel_ids=frozenset({-100999999}),
        )
        self.assertTrue(context.allowed)
        self.assertEqual(workspace.id, context.workspace_id)
        self.assertEqual(-100820001, context.primary_channel_id)
        self.assertEqual((-100820001, -100820002), context.channel_ids)
        self.assertEqual((-100820003,), context.discussion_chat_ids)

    async def test_disabled_module_is_not_live_ingest_source(self) -> None:
        workspace = await self._create_workspace(
            user_id=2301,
            name="Disabled",
            analytics_enabled=False,
        )
        await WorkspaceRepository(self.database).upsert_channel(
            workspace_id=workspace.id,
            kind="analytics",
            chat_id=-100830001,
        )
        value = await resolve_analytics_ingest_workspace(
            self.database,
            chat_id=-100830001,
            system_channel_ids=frozenset(),
        )
        self.assertIsNone(value)

    async def test_personal_ingest_resolves_same_alias_only_in_owner_workspace(self) -> None:
        first = await self._create_workspace(user_id=2401, name="Aliases First")
        second = await self._create_workspace(user_id=2402, name="Aliases Second")
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
        parsed = ParsedChannelPost(
            channel_id=-100840001,
            message_id=77,
            publication_key="message:77",
            posted_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
            edited_at=None,
            title="Personal analytics",
            username=None,
            author_signature=None,
            text_content="#Каэль",
            media_type="photo",
            media_group_id=None,
            has_spoiler=False,
            view_count=0,
            forward_count=0,
            message_url=None,
            hashtags=(("Каэль", "каэль"),),
            links=(),
            prompt=PromptSignals(
                is_prompt=False,
                score=0,
                has_important=False,
                has_strict=False,
                has_negative=False,
                has_technical=False,
                has_palette=False,
            ),
        )
        with patch(
            "velvet_bot.domains.workspaces.analytics_ingest.parse_channel_post",
            new=Mock(return_value=parsed),
        ):
            await ingest_workspace_channel_post(
                self.database,
                SimpleNamespace(),
                workspace_id=first.id,
            )
        async with self.database.acquire() as connection:
            character_id = await connection.fetchval(
                """
                SELECT hashtag.character_id
                FROM channel_post_hashtags AS hashtag
                JOIN channel_posts AS post ON post.id = hashtag.post_id
                WHERE post.channel_id = $1::BIGINT
                  AND hashtag.normalized_hashtag = 'каэль'
                """,
                parsed.channel_id,
            )
        self.assertEqual(first_character.id, int(character_id))
        self.assertNotEqual(second_character.id, int(character_id))


if __name__ == "__main__":
    unittest.main()
