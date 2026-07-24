from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.watermark.models import (
    WatermarkJob,
    WatermarkRevision,
    WatermarkSettings,
    WatermarkWorkItem,
)
from velvet_bot.krita_supervisor import wake_krita
from velvet_bot.supervisor_client import SupervisorClientError
from velvet_bot.watermark_ui import build_watermark_keyboard, format_watermark_caption

ROOT = Path(__file__).resolve().parents[1]


def _item(status: str, *, archive_media_id: int | None = None) -> WatermarkWorkItem:
    now = datetime.now(UTC)
    source_message_id = -archive_media_id if archive_media_id is not None else 9
    return WatermarkWorkItem(
        job=WatermarkJob(
            id=41,
            owner_user_id=7,
            chat_id=8,
            source_message_id=source_message_id,
            source_file_id="file",
            source_file_unique_id="unique",
            source_path="source.png",
            status="active",
            current_revision=1,
            control_message_id=None,
            preview_message_id=None,
            final_path=None,
            created_at=now,
            updated_at=now,
            workspace_id=3,
        ),
        revision=WatermarkRevision(
            job_id=41,
            revision=1,
            settings=WatermarkSettings(),
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


def _labels(item: WatermarkWorkItem) -> list[str]:
    keyboard = build_watermark_keyboard(item)
    return [button.text for row in keyboard.inline_keyboard for button in row]


class CanonicalWatermarkUiTests(unittest.TestCase):
    def test_draft_ui_requires_explicit_generation(self) -> None:
        labels = _labels(_item("draft"))

        self.assertIn("▶️ Сгенерировать preview", labels)
        self.assertNotIn("✅ Скачать PNG без сжатия", labels)
        self.assertIn("черновик:", format_watermark_caption(_item("draft")))

    def test_pending_ui_is_read_only(self) -> None:
        labels = _labels(_item("pending"))

        self.assertIn("⏳ Генерация выполняется", labels)
        self.assertNotIn("Прозр. +", labels)
        self.assertNotIn("▶️ Сгенерировать preview", labels)

    def test_error_ui_can_retry_generation(self) -> None:
        item = _item("error")
        labels = _labels(item)

        self.assertIn("▶️ Сгенерировать preview", labels)
        self.assertIn("ошибка:", format_watermark_caption(item))

    def test_ready_archive_ui_keeps_archive_review_actions(self) -> None:
        labels = _labels(_item("ready", archive_media_id=77))

        self.assertIn("✅ Использовать watermark", labels)
        self.assertIn("🔄 Переделать", labels)


class KritaWakeContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_supervisor_is_a_valid_noop(self) -> None:
        with patch(
            "velvet_bot.krita_supervisor.build_krita_supervisor_client",
            return_value=None,
        ):
            self.assertIsNone(await wake_krita(context="test"))

    async def test_supervisor_error_is_returned_for_user_feedback(self) -> None:
        client = SimpleNamespace(
            ensure_krita=AsyncMock(side_effect=SupervisorClientError("offline"))
        )
        with patch(
            "velvet_bot.krita_supervisor.build_krita_supervisor_client",
            return_value=client,
        ):
            self.assertEqual("offline", await wake_krita(context="test"))

    async def test_supervisor_is_called_once(self) -> None:
        client = SimpleNamespace(ensure_krita=AsyncMock(return_value={"ok": True}))
        with patch(
            "velvet_bot.krita_supervisor.build_krita_supervisor_client",
            return_value=client,
        ):
            self.assertIsNone(await wake_krita(context="test"))
        client.ensure_krita.assert_awaited_once_with()


class WatermarkPresentationArchitectureTests(unittest.TestCase):
    def test_workspace_installer_does_not_patch_watermark_ui_or_wake_policy(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_product_experience.py"
        ).read_text(encoding="utf-8")

        for forbidden in (
            "watermark_ui.build_watermark_keyboard =",
            "watermark_ui.format_watermark_caption =",
            "core_watermark.build_watermark_keyboard =",
            "core_watermark.format_watermark_caption =",
            "core_watermark._wake_krita =",
            "watermark_actions._wake_krita =",
            "watermark_service_module",
            "def _draft_watermark_keyboard",
            "def _draft_watermark_caption",
            "def _defer_krita_start",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("watermark_ui.build_watermark_keyboard", source)
        self.assertIn("watermark_ui.format_watermark_caption", source)
        self.assertIn("wake_krita(context=", source)

    def test_draft_creation_and_form_opening_do_not_wake_krita(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "watermark.py"
        ).read_text(encoding="utf-8")
        create_segment = source[
            source.index("async def _create_job_from_message(") : source.index(
                "async def _safe_edit("
            )
        ]
        start_segment = source[
            source.index('if action in {"start", "help"}:') : source.index(
                'if action == "menu":'
            )
        ]

        self.assertNotIn("wake_krita(", create_segment)
        self.assertNotIn("wake_krita(", start_segment)
        self.assertIn("Krita запустится только после", start_segment)

    def test_public_archive_uses_shared_wake_contract(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/public_archive/"
            "watermark_actions.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("async def _wake_krita", source)
        self.assertIn('wake_krita(context="public archive watermark")', source)


if __name__ == "__main__":
    unittest.main()
