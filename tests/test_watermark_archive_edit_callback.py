from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.presentation.telegram.routers.core_operations_controllers import (
    watermark as watermark_controller,
)


class ArchiveWatermarkEditCallbackTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _callback():
        return SimpleNamespace(
            answer=AsyncMock(),
            from_user=SimpleNamespace(id=7221553045),
            message=None,
        )

    async def test_archive_edit_uses_owner_checked_service_lookup(self) -> None:
        callback = self._callback()
        callback_data = SimpleNamespace(action="archive_edit", job_id=40, value="")
        item = SimpleNamespace(job=SimpleNamespace(archive_media_id=77))
        service = SimpleNamespace(get_current=AsyncMock(return_value=item))
        safe_edit = AsyncMock()

        with (
            patch.object(watermark_controller, "_watermark_enabled", return_value=True),
            patch.object(watermark_controller, "_build_service", return_value=service),
            patch.object(
                watermark_controller,
                "format_watermark_caption",
                return_value="caption",
            ),
            patch.object(
                watermark_controller,
                "build_archive_watermark_edit_keyboard",
                return_value="keyboard",
            ),
            patch.object(watermark_controller, "_safe_edit", safe_edit),
        ):
            await watermark_controller.handle_watermark_callback(
                callback,
                callback_data,
                bot=SimpleNamespace(),
                database=SimpleNamespace(),
            )

        service.get_current.assert_awaited_once_with(
            40,
            owner_user_id=7221553045,
        )
        callback.answer.assert_awaited_once_with("Настройки открыты.")
        safe_edit.assert_awaited_once_with(
            callback,
            "caption",
            item,
            keyboard="keyboard",
        )

    async def test_missing_or_foreign_archive_job_returns_alert(self) -> None:
        callback = self._callback()
        callback_data = SimpleNamespace(action="archive_edit", job_id=40, value="")
        service = SimpleNamespace(
            get_current=AsyncMock(
                side_effect=ValueError("Это задание принадлежит другому владельцу.")
            )
        )
        safe_edit = AsyncMock()

        with (
            patch.object(watermark_controller, "_watermark_enabled", return_value=True),
            patch.object(watermark_controller, "_build_service", return_value=service),
            patch.object(watermark_controller, "_safe_edit", safe_edit),
        ):
            await watermark_controller.handle_watermark_callback(
                callback,
                callback_data,
                bot=SimpleNamespace(),
                database=SimpleNamespace(),
            )

        callback.answer.assert_awaited_once_with(
            "Архивное задание не найдено.",
            show_alert=True,
        )
        safe_edit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
