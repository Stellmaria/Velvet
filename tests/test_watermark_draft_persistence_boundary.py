from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.watermark.models import (
    WatermarkJob,
    WatermarkRevision,
    WatermarkSettings,
    WatermarkWorkItem,
)
from velvet_bot.domains.watermark.service import WatermarkService

ROOT = Path(__file__).resolve().parents[1]


def _item(*, status: str = "draft", revision: int = 1) -> WatermarkWorkItem:
    now = datetime.now(UTC)
    return WatermarkWorkItem(
        job=WatermarkJob(
            id=41,
            owner_user_id=7,
            chat_id=8,
            source_message_id=9,
            source_file_id="file",
            source_file_unique_id="unique",
            source_path="source.png",
            status="active",
            current_revision=revision,
            control_message_id=None,
            preview_message_id=None,
            final_path=None,
            created_at=now,
            updated_at=now,
            workspace_id=3,
        ),
        revision=WatermarkRevision(
            job_id=41,
            revision=revision,
            settings=WatermarkSettings(position="top_left"),
            status=status,
            request_path=None,
            output_path=None,
            response_path=None,
            telegram_preview_file_id=None,
            error=None,
            created_at=now,
            completed_at=None,
        ),
    )


class WatermarkDraftServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.repository = SimpleNamespace(
            create_job=AsyncMock(return_value=_item()),
            get_current=AsyncMock(return_value=_item()),
            create_revision=AsyncMock(return_value=_item(revision=2)),
            undo=AsyncMock(return_value=_item(revision=2)),
            queue_revision=AsyncMock(return_value=_item(status="pending")),
        )
        self.service = WatermarkService(
            bot=SimpleNamespace(),
            repository=self.repository,  # type: ignore[arg-type]
            bridge=SimpleNamespace(),  # type: ignore[arg-type]
        )

    async def test_create_job_can_persist_draft_revision(self) -> None:
        settings = WatermarkSettings(position="top_right")

        await self.service.create_job(
            owner_user_id=7,
            chat_id=8,
            source_message_id=9,
            source_file_id="file",
            source_file_unique_id="unique",
            source_path="source.png",
            settings=settings,
            draft=True,
            workspace_id=3,
        )

        kwargs = self.repository.create_job.await_args.kwargs
        self.assertEqual("draft", kwargs["revision_status"])
        self.assertEqual(settings, kwargs["settings"])

    async def test_revise_can_create_draft_without_queueing(self) -> None:
        await self.service.revise(
            41,
            owner_user_id=7,
            opacity_delta=5,
            draft=True,
        )

        kwargs = self.repository.create_revision.await_args.kwargs
        self.assertEqual("draft", kwargs["revision_status"])
        self.assertEqual(75, kwargs["settings"].opacity)

    async def test_undo_can_restore_previous_settings_as_draft(self) -> None:
        await self.service.undo(41, owner_user_id=7, draft=True)

        self.repository.undo.assert_awaited_once_with(
            41,
            revision_status="draft",
        )

    async def test_generate_queues_current_draft(self) -> None:
        result = await self.service.generate(41, owner_user_id=7)

        self.assertEqual("pending", result.revision.status)
        self.repository.queue_revision.assert_awaited_once_with(
            job_id=41,
            revision=1,
        )

    async def test_generate_rejects_already_queued_revision(self) -> None:
        self.repository.get_current.return_value = _item(status="processing")

        with self.assertRaisesRegex(ValueError, "уже запущена"):
            await self.service.generate(41, owner_user_id=7)

        self.repository.queue_revision.assert_not_awaited()


class WatermarkDraftPresentationBoundaryTests(unittest.TestCase):
    def test_workspace_controller_has_no_watermark_persistence_or_service_monkeypatch(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_product_experience.py"
        ).read_text(encoding="utf-8")

        for forbidden in (
            "INSERT INTO watermark_jobs",
            "INSERT INTO watermark_revisions",
            "UPDATE watermark_revisions",
            "repository._database",
            "repository._map_job",
            "repository._map_revision",
            "WatermarkService.create_job =",
            "WatermarkService.revise =",
            "WatermarkService.undo =",
            'setattr(WatermarkService, "generate"',
            "async def _service_create_draft_job",
            "async def _service_generate",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("await service.generate(", source)
        self.assertIn("draft=True", source)

    def test_core_watermark_explicitly_creates_draft_with_workspace_template(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "watermark.py"
        ).read_text(encoding="utf-8")

        self.assertIn("WorkspaceWatermarkTemplateRepository(database).get", source)
        self.assertIn("settings=settings", source)
        self.assertIn("draft=True", source)


if __name__ == "__main__":
    unittest.main()
