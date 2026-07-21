from __future__ import annotations

import unittest

from velvet_bot.ai_quality import AIQualitySummary
from velvet_bot.domains.media_rework import MediaReworkSummary
from velvet_bot.owner_menu import build_owner_main_keyboard
from velvet_bot.quality_ui import QualityCallback
from velvet_bot.velvet_ai_ui import build_velvet_ai_menu


def _quality_summary() -> AIQualitySummary:
    return AIQualitySummary(
        pending=2,
        processing=1,
        ready=10,
        errors=3,
        skipped=1,
        unreviewed=4,
        accepted=5,
        fix_required=1,
        clean=6,
        warnings=3,
        critical=1,
    )


def _rework_summary() -> MediaReworkSummary:
    return MediaReworkSummary(
        active=5,
        needs_fix=3,
        checking=1,
        ready_for_review=1,
        stel_priority=2,
        qwen_only=3,
    )


class VelvetAIMenuTests(unittest.TestCase):
    def test_owner_menu_opens_qwen_panel(self) -> None:
        keyboard = build_owner_main_keyboard()
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        qwen = [button for button in buttons if button.text == "🤖 Qwen"]

        self.assertEqual(1, len(qwen))
        self.assertIn("ai_menu", qwen[0].callback_data or "")

    def test_qwen_panel_contains_all_archive_and_manual_operations(self) -> None:
        text, keyboard = build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
            quality=_quality_summary(),
            rework=_rework_summary(),
        )
        actions = {
            QualityCallback.unpack(button.callback_data).action
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("quality:")
        }

        self.assertIn("Qwen · работа с архивом", text)
        self.assertIn("Стэл <b>2</b> · Qwen <b>3</b>", text)
        self.assertTrue(
            {
                "quality_ops",
                "reworks",
                "qchecks",
                "quality_run",
                "quality_recent",
                "quality_retry_errors",
                "qcal",
                "refcompare_start",
                "promptcheck_start",
                "visual_start",
                "format_menu",
                "sets",
                "setreports",
                "aijobs",
                "menu",
                "ai_menu",
                "close",
            }.issubset(actions)
        )

    def test_qwen_and_owner_buttons_are_mobile_compact(self) -> None:
        _, qwen_keyboard = build_velvet_ai_menu(
            enabled=False,
            provider="ollama",
            model="qwen3-vl:8b",
            quality=_quality_summary(),
            rework=_rework_summary(),
        )
        owner_keyboard = build_owner_main_keyboard()

        for keyboard in (qwen_keyboard, owner_keyboard):
            for row in keyboard.inline_keyboard:
                self.assertLessEqual(len(row), 2)
                for button in row:
                    self.assertLessEqual(len(button.text), 24)
                    if button.callback_data:
                        self.assertLessEqual(
                            len(button.callback_data.encode("utf-8")),
                            64,
                        )


if __name__ == "__main__":
    unittest.main()
