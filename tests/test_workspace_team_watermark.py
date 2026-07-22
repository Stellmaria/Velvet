from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import asyncpg
from PIL import Image

from velvet_bot.database import Database
from velvet_bot.domains.watermark.models import WatermarkSettings
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.team_repository import WorkspaceTeamRepository
from velvet_bot.domains.workspaces.team_service import WorkspaceTeamService
from velvet_bot.domains.workspaces.watermark_assets import (
    WorkspaceWatermarkAssetRepository,
    WorkspaceWatermarkAssetService,
    prepare_watermark_asset,
)
from velvet_bot.infrastructure.krita_bridge import KritaBridge

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceTeamWatermarkContractTests(unittest.TestCase):
    def test_migration_protects_last_owner_and_snapshots_logo(self) -> None:
        source = (ROOT / "migrations/909_workspace_team_watermarks.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("workspace_watermark_assets", source)
        self.assertIn("protect_last_workspace_owner", source)
        self.assertIn("pg_advisory_xact_lock(OLD.workspace_id)", source)
        self.assertIn("ADD COLUMN IF NOT EXISTS logo_kind", source)
        self.assertIn("watermark_jobs_logo_snapshot_check", source)

    def test_personal_routers_precede_generic_workspace_router(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        generic = source.index("router.include_router(workspaces_router)")
        self.assertLess(source.index("router.include_router(workspace_team_router)"), generic)
        self.assertLess(
            source.index("router.include_router(workspace_watermark_router)"), generic
        )

    def test_access_policy_has_guarded_team_logo_and_watermark_routes(self) -> None:
        source = (ROOT / "velvet_bot/core/access/policy.py").read_text(encoding="utf-8")
        self.assertIn('"watermark"', source)
        self.assertIn('"wteam:"', source)
        self.assertIn('"wlogo:"', source)
        self.assertIn('"wm:"', source)

    def test_bridge_and_plugin_support_logo_schema_v2(self) -> None:
        bridge = (ROOT / "velvet_bot/infrastructure/krita_bridge.py").read_text(
            encoding="utf-8"
        )
        plugin = (ROOT / "tools/krita/velvet_logo/velvet_logo.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"schema_version": 2', bridge)
        self.assertIn('"logo": logo', bridge)
        self.assertIn("self.paths.assets", bridge)
        self.assertIn("data:image/png;base64", plugin)
        self.assertIn("ET.fromstring(source.read_bytes())", plugin)


class WorkspaceWatermarkValidationTests(unittest.TestCase):
    @staticmethod
    def _png(*, transparent: bool) -> bytes:
        image = Image.new("RGBA", (32, 16), (20, 30, 40, 0 if transparent else 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_transparent_png_is_normalized(self) -> None:
        prepared = prepare_watermark_asset(
            self._png(transparent=True),
            file_name="logo.png",
            mime_type="image/png",
        )
        self.assertEqual("png", prepared.asset_kind)
        self.assertTrue(prepared.has_alpha)
        self.assertEqual((32.0, 16.0), (prepared.width, prepared.height))

    def test_opaque_png_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "прозрач"):
            prepare_watermark_asset(
                self._png(transparent=False),
                file_name="logo.png",
                mime_type="image/png",
            )

    def test_safe_svg_is_sanitized(self) -> None:
        prepared = prepare_watermark_asset(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">'
            b'<path d="M0 0h100v50z" fill="#fff"/></svg>',
            file_name="logo.svg",
            mime_type="image/svg+xml",
        )
        self.assertEqual("svg", prepared.asset_kind)
        self.assertEqual((100.0, 50.0), (prepared.width, prepared.height))

    def test_svg_script_and_external_href_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "script"):
            prepare_watermark_asset(
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                b'<script>alert(1)</script></svg>',
                file_name="bad.svg",
                mime_type="image/svg+xml",
            )
        with self.assertRaisesRegex(ValueError, "Внешние"):
            prepare_watermark_asset(
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                b'<image href="https://example.com/a.png"/></svg>',
                file_name="bad.svg",
                mime_type="image/svg+xml",
            )


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceTeamWatermarkTests(unittest.IsolatedAsyncioTestCase):
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
                    watermark_revisions,
                    watermark_jobs,
                    workspace_watermark_assets
                RESTART IDENTITY CASCADE
                """
            )
            await connection.execute(
                "DELETE FROM workspaces WHERE id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute("DELETE FROM user_workspace_preferences")
            await connection.execute("DELETE FROM user_public_workspace_preferences")
            await connection.execute("DELETE FROM workspace_creation_grants")

    async def _workspace(self, *, owner_id: int, name: str) -> SimpleNamespace:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspaces (slug, name, is_system)
                VALUES ($1::VARCHAR, $2::VARCHAR, FALSE)
                RETURNING id
                """,
                f"team-{owner_id}",
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
                owner_id,
            )
            await connection.execute(
                """
                INSERT INTO workspace_settings (workspace_id)
                VALUES ($1::BIGINT)
                """,
                workspace_id,
            )
            await connection.execute(
                """
                INSERT INTO workspace_modules (
                    workspace_id, module_key, is_allowed, is_enabled
                )
                VALUES
                    ($1::BIGINT, 'team', TRUE, TRUE),
                    ($1::BIGINT, 'watermark', TRUE, TRUE)
                """,
                workspace_id,
            )
        return SimpleNamespace(id=workspace_id, owner_id=owner_id)

    def _team(self) -> WorkspaceTeamService:
        return WorkspaceTeamService(
            repository=WorkspaceTeamRepository(self.database),
            workspaces=WorkspaceService(WorkspaceRepository(self.database)),
        )

    async def test_database_rejects_removing_or_demoting_last_owner(self) -> None:
        workspace = await self._workspace(owner_id=3001, name="Owner Guard")
        repository = WorkspaceTeamRepository(self.database)
        with self.assertRaises(asyncpg.CheckViolationError):
            await repository.change_role(
                workspace_id=workspace.id,
                user_id=workspace.owner_id,
                role="admin",
            )
        with self.assertRaises(asyncpg.CheckViolationError):
            await repository.remove_member(
                workspace_id=workspace.id,
                user_id=workspace.owner_id,
            )

    async def test_owner_can_add_admin_and_demote_co_owner(self) -> None:
        workspace = await self._workspace(owner_id=3101, name="Owner Powers")
        service = self._team()
        admin = await service.add_member(
            workspace_id=workspace.id,
            actor_user_id=workspace.owner_id,
            user_id=3102,
            role="admin",
        )
        self.assertEqual("admin", admin.role)
        await service.add_member(
            workspace_id=workspace.id,
            actor_user_id=workspace.owner_id,
            user_id=3103,
            role="owner",
        )
        changed = await service.change_role(
            workspace_id=workspace.id,
            actor_user_id=workspace.owner_id,
            user_id=3103,
            role="editor",
        )
        self.assertEqual("editor", changed.role)

    async def test_admin_cannot_grant_admin_or_modify_owner(self) -> None:
        workspace = await self._workspace(owner_id=3201, name="Admin Limits")
        service = self._team()
        await service.add_member(
            workspace_id=workspace.id,
            actor_user_id=workspace.owner_id,
            user_id=3202,
            role="admin",
        )
        with self.assertRaises(WorkspaceAccessError):
            await service.add_member(
                workspace_id=workspace.id,
                actor_user_id=3202,
                user_id=3203,
                role="admin",
            )
        with self.assertRaises(WorkspaceAccessError):
            await service.change_role(
                workspace_id=workspace.id,
                actor_user_id=3202,
                user_id=workspace.owner_id,
                role="viewer",
            )

    async def test_member_lists_are_workspace_scoped(self) -> None:
        first = await self._workspace(owner_id=3301, name="First")
        second = await self._workspace(owner_id=3302, name="Second")
        await self._team().add_member(
            workspace_id=first.id,
            actor_user_id=first.owner_id,
            user_id=3303,
            role="viewer",
        )
        first_ids = {
            item.user_id
            for item in await self._team().list_members(
                workspace_id=first.id,
                actor_user_id=first.owner_id,
            )
        }
        second_ids = {
            item.user_id
            for item in await self._team().list_members(
                workspace_id=second.id,
                actor_user_id=second.owner_id,
            )
        }
        self.assertEqual({3301, 3303}, first_ids)
        self.assertEqual({3302}, second_ids)

    async def test_workspace_asset_and_job_snapshot_do_not_cross_or_mutate(self) -> None:
        first = await self._workspace(owner_id=3401, name="Logo First")
        second = await self._workspace(owner_id=3402, name="Logo Second")
        with tempfile.TemporaryDirectory() as directory:
            bridge = KritaBridge(directory)
            service = WorkspaceWatermarkAssetService(
                repository=WorkspaceWatermarkAssetRepository(self.database),
                bridge_paths=bridge.paths,
            )
            transparent = WorkspaceWatermarkValidationTests._png(transparent=True)
            first_asset = await service.store(
                workspace_id=first.id,
                raw=transparent,
                file_name="first.png",
                mime_type="image/png",
                telegram_file_id="first-file",
                telegram_file_unique_id="first-unique",
                uploaded_by=first.owner_id,
            )
            self.assertIsNone(await service.get(second.id))
            source = bridge.paths.sources / "source.png"
            source.write_bytes(transparent)
            job = await WatermarkRepository(self.database).create_job(
                owner_user_id=first.owner_id,
                chat_id=1,
                source_message_id=2,
                source_file_id="source-file",
                source_file_unique_id="source-unique",
                source_path=str(source),
                settings=WatermarkSettings(),
                workspace_id=first.id,
                logo_kind=first_asset.asset_kind,
                logo_path=first_asset.local_path,
                logo_width=first_asset.width,
                logo_height=first_asset.height,
                logo_name=first_asset.file_name,
            )
            replacement = await service.store(
                workspace_id=first.id,
                raw=WorkspaceWatermarkValidationTests._png(transparent=True),
                file_name="replacement.png",
                mime_type="image/png",
                telegram_file_id="second-file",
                telegram_file_unique_id="second-unique",
                uploaded_by=first.owner_id,
            )
            current = await WatermarkRepository(self.database).get_current(job.job.id)
            assert current is not None
            self.assertEqual(first_asset.local_path, current.job.logo_path)
            self.assertEqual("first.png", current.job.logo_name)
            self.assertEqual("replacement.png", replacement.file_name)


if __name__ == "__main__":
    unittest.main()
