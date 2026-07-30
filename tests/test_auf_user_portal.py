from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.app.auf_user_portal_install import (
    _task_line,
    _user_settings_text,
    _video_review_keyboard,
    _wallet_keyboard_with_tasks,
)


class AufUserPortalKeyboardTests(unittest.TestCase):
    def test_video_review_button_shows_auf_price(self) -> None:
        keyboard = _video_review_keyboard(
            workspace_id=17,
            quoted_units=45_000,
            can_submit=True,
        )
        self.assertEqual("Запустить · 4.5 Ауф", keyboard.inline_keyboard[0][0].text)
        callback_data = keyboard.inline_keyboard[0][0].callback_data or ""
        self.assertIn("submit", callback_data)
        self.assertNotIn("$", callback_data)

    def test_insufficient_balance_replaces_submit_with_refresh(self) -> None:
        keyboard = _video_review_keyboard(
            workspace_id=17,
            quoted_units=45_000,
            can_submit=False,
        )
        self.assertEqual(
            "Пересчитать баланс и цену",
            keyboard.inline_keyboard[0][0].text,
        )
        self.assertNotIn(
            "Запустить",
            " ".join(
                button.text
                for row in keyboard.inline_keyboard
                for button in row
            ),
        )

    def test_wallet_tasks_button_is_inserted_before_back(self) -> None:
        def original(**_kwargs) -> InlineKeyboardMarkup:
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Пакет", callback_data="package")],
                    [InlineKeyboardButton(text="Назад", callback_data="back")],
                ]
            )

        keyboard = _wallet_keyboard_with_tasks(
            original,
            workspace_id=17,
            global_owner=False,
            frozen=False,
            invoices=(),
        )
        self.assertEqual("🧾 Мои задачи", keyboard.inline_keyboard[-2][0].text)
        self.assertEqual("Назад", keyboard.inline_keyboard[-1][0].text)


class AufUserPortalPresentationTests(unittest.TestCase):
    def test_video_settings_hide_provider_money(self) -> None:
        captured: dict[str, object] = {}

        def original(**kwargs) -> str:
            captured.update(kwargs)
            return "Параметры"

        text = _user_settings_text(
            original,
            model="grok",
            resolution="480p",
            duration=6,
            generate_audio=False,
            wan_mode="first",
            has_last_frame=False,
            estimated_usd=object(),
            estimated_rub=object(),
            cost_change={"old_usd": "1"},
        )
        self.assertIsNone(captured["estimated_usd"])
        self.assertIsNone(captured["estimated_rub"])
        self.assertIsNone(captured["cost_change"])
        self.assertIn("цена в Ауф", text)
        self.assertNotIn("$", text)

    def test_task_line_contains_only_user_facing_charge(self) -> None:
        line = _task_line(
            {
                "id": "12345678-aaaa-bbbb-cccc-123456789012",
                "status": "success",
                "payload": {
                    "request": {
                        "model": "grok_imagine_video",
                        "resolution": "720p",
                        "duration_seconds": 6,
                    }
                },
                "quoted_units": 45_000,
                "charge_status": "captured",
                "created_at": datetime(2026, 7, 30, 7, 0, tzinfo=timezone.utc),
            }
        )
        self.assertIn("Grok Imagine v1", line)
        self.assertIn("4.5 Ауф", line)
        self.assertIn("списано", line)
        self.assertNotIn("provider", line.casefold())
        self.assertNotIn("$", line)

    def test_task_query_is_scoped_by_user_and_workspace(self) -> None:
        source = Path(
            "velvet_bot/app/auf_user_portal_install.py"
        ).read_text(encoding="utf-8")
        self.assertIn("task.created_by = $2::BIGINT", source)
        self.assertIn("task.payload ->> 'workspace_id' = $3::TEXT", source)
        self.assertIn("Системные задачи, другие участники", source)


if __name__ == "__main__":
    unittest.main()
