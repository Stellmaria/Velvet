from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.watermark.archive_output import ArchiveWatermarkOutput
from velvet_bot.domains.watermark.models import (
    WatermarkJob,
    WatermarkRevision,
    WatermarkSettings,
    WatermarkWorkItem,
)
from velvet_bot.domains.watermark.telegram_storage import (
    DEFAULT_WATERMARK_STORAGE_CHAT_ID,
    DEFAULT_WATERMARK_STORAGE_THREAD_ID,
    WatermarkStorageSettings,
    cleanup_watermark_job_files,
    storage_caption,
    storage_file_name,
    storage_message_link,
)
from velvet_bot.infrastructure.krita_bridge import KritaBridge
from velvet_bot.presentation.telegram.archive_watermark_storage import (
    _configured_storage_settings,
)


def _item(source_path: Path, *, job_id: int = 12, revision: int = 2) -> WatermarkWorkItem:
    now = datetime.now(UTC)
    return WatermarkWorkItem(
        job=WatermarkJob(
            id=job_id,
            owner_user_id=7221553045,
            chat_id=10,
            source_message_id=-77,
            source_file_id="source-file",
            source_file_unique_id="source-unique",
            source_path=str(source_path),
            status="approved",
            current_revision=revision,
            control_message_id=None,
            preview_message_id=None,
            final_path=None,
            created_at=now,
            updated_at=now,
        ),
        revision=WatermarkRevision(
            job_id=job_id,
            revision=revision,
            settings=WatermarkSettings(),
            status="ready",
            request_path=None,
            output_path=None,
            response_path=None,
            telegram_preview_file_id=None,
            error=None,
            created_at=now,
            completed_at=now,
        ),
    )


class WatermarkTelegramStorageTests(unittest.TestCase):
    def test_requested_storage_is_the_default(self) -> None:
        self.assertEqual(-1004459280894, DEFAULT_WATERMARK_STORAGE_CHAT_ID)
        self.assertEqual(3, DEFAULT_WATERMARK_STORAGE_THREAD_ID)
        settings = WatermarkStorageSettings.from_env()
        self.assertEqual(-1004459280894, settings.chat_id)
        self.assertEqual(3, settings.thread_id)

    def test_storage_name_caption_and_link_are_searchable(self) -> None:
        item = _item(Path("source.png"))
        output = ArchiveWatermarkOutput(
            path=Path("output.png"),
            width=2048,
            height=3072,
            source_bytes=12_000_000,
            output_bytes=12_500_000,
        )
        digest = "a" * 64
        file_name = storage_file_name(
            media_id=77,
            job_id=12,
            revision=2,
            sha256=digest,
        )
        caption = storage_caption(
            media_id=77,
            job_id=12,
            revision=2,
            sha256=digest,
            output=output,
            source_name="lane-original.png",
            character_names=("Лейн", "Каэль"),
            item=item,
        )

        self.assertEqual("velvet-wm-m77-j12-r2-aaaaaaaaaaaa.png", file_name)
        self.assertIn("#media_77", caption)
        self.assertIn("#job_12", caption)
        self.assertIn("#rev_2", caption)
        self.assertIn("Лейн, Каэль", caption)
        self.assertIn(digest, caption)
        self.assertEqual(
            "https://t.me/c/4459280894/91",
            storage_message_link(-1004459280894, 91),
        )

    def test_cleanup_removes_only_one_job_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bridge = KritaBridge(Path(directory))
            source = bridge.paths.sources / "archive-source.png"
            source.write_bytes(b"source")
            item = _item(source)

            expected = [source]
            for folder, suffix in (
                (bridge.paths.requests, ".json"),
                (bridge.paths.responses, ".json"),
                (bridge.paths.outputs, ".png"),
                (bridge.paths.previews, ".jpg"),
            ):
                path = folder / f"job-12-r2{suffix}"
                path.write_bytes(b"watermark-data")
                expected.append(path)

            unrelated = bridge.paths.outputs / "job-99-r1.png"
            unrelated.write_bytes(b"keep")

            deleted, freed = cleanup_watermark_job_files(item, bridge)

            self.assertEqual(len(expected), deleted)
            self.assertGreater(freed, 0)
            self.assertTrue(all(not path.exists() for path in expected))
            self.assertTrue(unrelated.exists())

    def test_migration_and_handler_registration_are_present(self) -> None:
        migration = Path("migrations/z002_watermark_telegram_storage.sql").read_text(
            encoding="utf-8"
        )
        owner_menu = Path(
            "velvet_bot/presentation/telegram/routers/"
            "core_operations_controllers/owner_menu.py"
        ).read_text(encoding="utf-8")
        handler = Path(
            "velvet_bot/presentation/telegram/archive_watermark_storage.py"
        ).read_text(encoding="utf-8")

        self.assertIn("watermark_storage_message_id", migration)
        self.assertIn("watermark_storage_sha256", migration)
        self.assertIn("register_archive_watermark_storage_handler(router)", owner_menu)
        self.assertLess(
            owner_menu.index("register_archive_watermark_storage_handler(router)"),
            owner_menu.index("router.include_router(watermark_router)"),
        )
        self.assertIn('F.action == "archive_approve"', handler)
        self.assertIn('Command("wm_file", "wm_storage")', handler)
        self.assertIn('Command("wm_download")', handler)
        self.assertIn("store_archive_watermark", handler)
        self.assertIn("cleanup_watermark_job_files", handler)
        self.assertNotIn("callback.message.answer_document", handler)


class WorkspaceWatermarkStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_personal_job_uses_configured_channel_and_topic(self) -> None:
        destination = SimpleNamespace(
            destination_key="watermarks",
            chat_id=-10077,
            message_thread_id=19,
        )
        with patch(
            "velvet_bot.presentation.telegram.archive_watermark_storage."
            "WorkspaceOnboardingRepository.list_destinations",
            new=AsyncMock(return_value=(destination,)),
        ):
            settings = await _configured_storage_settings(
                SimpleNamespace(),
                workspace_id=5,
            )

        self.assertIsNotNone(settings)
        assert settings is not None
        self.assertEqual(-10077, settings.chat_id)
        self.assertEqual(19, settings.thread_id)

    async def test_personal_job_without_destination_uses_runtime_fallback(self) -> None:
        with patch(
            "velvet_bot.presentation.telegram.archive_watermark_storage."
            "WorkspaceOnboardingRepository.list_destinations",
            new=AsyncMock(return_value=()),
        ):
            settings = await _configured_storage_settings(
                SimpleNamespace(),
                workspace_id=5,
            )
        self.assertIsNone(settings)


if __name__ == "__main__":
    unittest.main()
