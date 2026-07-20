from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image

from velvet_bot.domains.archive import ArchivePage, ArchivedMedia
from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.domains.public_archive import PublicMediaState
from velvet_bot.domains.public_archive.watermark_repository import (
    PublicArchiveWatermarkRepository,
)
from velvet_bot.domains.watermark.archive_output import (
    prepare_archive_watermark_output,
)
from velvet_bot.domains.watermark.models import (
    WatermarkJob,
    WatermarkRevision,
    WatermarkSettings,
    WatermarkWorkItem,
)
from velvet_bot.public_manager_ui import build_manager_archive_keyboard
from velvet_bot.watermark_ui import (
    build_archive_watermark_edit_keyboard,
    build_watermark_keyboard,
)


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _work_item(*, source_message_id: int = -77) -> WatermarkWorkItem:
    now = datetime.now(UTC)
    settings = WatermarkSettings()
    return WatermarkWorkItem(
        job=WatermarkJob(
            id=12,
            owner_user_id=1,
            chat_id=2,
            source_message_id=source_message_id,
            source_file_id="source",
            source_file_unique_id=None,
            source_path="source.png",
            status="active",
            current_revision=1,
            control_message_id=None,
            preview_message_id=None,
            final_path=None,
            created_at=now,
            updated_at=now,
        ),
        revision=WatermarkRevision(
            job_id=12,
            revision=1,
            settings=settings,
            status="ready",
            request_path=None,
            output_path="output.png",
            response_path=None,
            telegram_preview_file_id="preview",
            error=None,
            created_at=now,
            completed_at=now,
        ),
    )


class WatermarkTemplateTests(unittest.TestCase):
    def test_requested_template_is_the_global_default(self) -> None:
        settings = WatermarkSettings().normalized()
        self.assertEqual("bottom_right", settings.position)
        self.assertEqual("auto", settings.color)
        self.assertEqual(70, settings.opacity)
        self.assertEqual(19.7, settings.size)
        self.assertEqual(4.4, settings.margin)

    def test_negative_source_message_marks_archive_job(self) -> None:
        self.assertEqual(77, _work_item().job.archive_media_id)
        self.assertIsNone(_work_item(source_message_id=44).job.archive_media_id)

    def test_archive_preview_starts_with_keep_or_edit_decision(self) -> None:
        keyboard = build_watermark_keyboard(_work_item())
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("✅ Оставить и заменить в архиве", labels)
        self.assertIn("⚙️ Изменить стандартный шаблон", labels)
        self.assertNotIn("✅ Скачать PNG без сжатия", labels)

        expanded = build_archive_watermark_edit_keyboard(_work_item())
        expanded_labels = [
            button.text for row in expanded.inline_keyboard for button in row
        ]
        self.assertIn("◐ Авто", expanded_labels)
        self.assertIn("✅ Оставить и заменить в архиве", expanded_labels)


class ArchiveOutputQualityTests(unittest.TestCase):
    def test_output_keeps_dimensions_and_is_not_smaller_than_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "output.png"
            Image.new("RGB", (64, 48), (20, 30, 40)).save(source, format="PNG")
            source.write_bytes(source.read_bytes() + (b"x" * 8192))
            Image.new("RGB", (64, 48), (20, 30, 40)).save(output, format="PNG")

            result = prepare_archive_watermark_output(source, output)

            self.assertEqual((64, 48), (result.width, result.height))
            self.assertGreaterEqual(result.output_bytes, result.source_bytes)
            with Image.open(output) as image:
                image.load()
                self.assertEqual((64, 48), image.size)

    def test_changed_dimensions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "output.png"
            Image.new("RGB", (64, 48)).save(source, format="PNG")
            Image.new("RGB", (63, 48)).save(output, format="PNG")
            with self.assertRaisesRegex(ValueError, "изменила размеры"):
                prepare_archive_watermark_output(source, output)


class ManagerWatermarkButtonTests(unittest.TestCase):
    def test_manager_card_has_fast_watermark_button(self) -> None:
        now = datetime.now(UTC)
        page = ArchivePage(
            character=CharacterRecord(
                id=3,
                name="Лейн",
                created_by=1,
                created_in_chat=2,
                created_at=now,
                archive_chat_id=None,
                archive_thread_id=None,
                archive_topic_url=None,
            ),
            media=ArchivedMedia(
                id=77,
                telegram_file_id="file",
                media_type="document",
                original_file_name="lane.png",
                storage_file_name="lane.png",
                mime_type="image/png",
                file_size=12_000_000,
                linked_at=now,
            ),
            offset=0,
            total=1,
        )
        keyboard = build_manager_archive_keyboard(
            page,
            PublicMediaState(0, False, False),
            category="female",
            universe="original",
            story_id=0,
        )
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        fast = next(button for button in buttons if "Быстрый watermark" in button.text)
        self.assertIn("pwm", fast.callback_data)


class WatermarkReplacementRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_approval_preserves_original_and_indexes_storage_message(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        database = SimpleNamespace(acquire=lambda: _AsyncContext(connection))
        repository = PublicArchiveWatermarkRepository(database)

        updated = await repository.approve_replacement(
            media_id=77,
            telegram_file_id="watermarked",
            telegram_file_unique_id="watermarked-unique",
            file_size=12_500_000,
            approved_by=7221553045,
            settings=WatermarkSettings(),
            storage_chat_id=-1004459280894,
            storage_thread_id=3,
            storage_message_id=44,
            storage_sha256="a" * 64,
        )

        self.assertTrue(updated)
        sql = connection.execute.await_args.args[0]
        self.assertIn("source_telegram_file_id = COALESCE", sql)
        self.assertIn("watermark_applied = TRUE", sql)
        self.assertIn("watermark_approved = TRUE", sql)
        self.assertIn("watermark_storage_chat_id", sql)
        self.assertIn("watermark_storage_message_id", sql)
        self.assertIn("watermark_storage_sha256", sql)
        self.assertNotIn("character_media", sql)
        template = json.loads(connection.execute.await_args.args[5])
        self.assertEqual("bottom_right", template["position"])
        self.assertEqual("auto", template["color"])
        self.assertEqual(-1004459280894, connection.execute.await_args.args[6])
        self.assertEqual(3, connection.execute.await_args.args[7])
        self.assertEqual(44, connection.execute.await_args.args[8])


if __name__ == "__main__":
    unittest.main()
