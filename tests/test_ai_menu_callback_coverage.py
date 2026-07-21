from __future__ import annotations

import re
import unittest
from pathlib import Path

from velvet_bot.ai_quality import AIQualitySummary
from velvet_bot.domains.media_rework import MediaReworkSummary
from velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_operations import (
    build_quality_operations_menu,
)
from velvet_bot.quality_ui import QualityCallback
from velvet_bot.velvet_ai_ui import build_velvet_ai_menu


ROOT = Path(__file__).resolve().parents[1]
_ACTION_RE = re.compile(r"F\.action\s*==\s*[\"']([^\"']+)[\"']")
_LITERAL_CALLBACK_RE = re.compile(
    r"(?:quality_callback\(\s*|QualityCallback\(\s*action\s*=\s*)"
    r"[\"']([^\"']+)[\"']"
)


def quality_actions(markup) -> set[str]:
    actions: set[str] = set()
    for row in markup.inline_keyboard:
        for button in row:
            callback_data = button.callback_data
            if not callback_data or not callback_data.startswith("quality:"):
                continue
            actions.add(QualityCallback.unpack(callback_data).action)
            if len(callback_data.encode("utf-8")) > 64:
                raise AssertionError(f"Callback превышает 64 байта: {callback_data}")
    return actions


def _active_controller_paths() -> tuple[Path, ...]:
    legacy = tuple((ROOT / "velvet_bot/handlers").glob("*.py"))
    canonical = tuple(
        (ROOT / "velvet_bot/presentation/telegram/routers").rglob("*.py")
    )
    return legacy + canonical


def registered_quality_actions() -> set[str]:
    actions: set[str] = set()
    for path in _active_controller_paths():
        actions.update(_ACTION_RE.findall(path.read_text(encoding="utf-8")))
    return actions


def literal_quality_actions() -> set[str]:
    actions: set[str] = set()
    for path in (ROOT / "velvet_bot").rglob("*.py"):
        actions.update(_LITERAL_CALLBACK_RE.findall(path.read_text(encoding="utf-8")))
    return actions


class AIMenuCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = AIQualitySummary(
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
        self.rework = MediaReworkSummary(
            active=5,
            needs_fix=3,
            checking=1,
            ready_for_review=1,
            stel_priority=2,
            qwen_only=3,
        )

    def _qwen_menu(self):
        return build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
            quality=self.summary,
            rework=self.rework,
        )

    def test_primary_panel_routes_to_operations_history_rework_and_reference(self) -> None:
        _, markup = self._qwen_menu()
        by_label = {
            button.text: button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }

        self.assertEqual(
            "quality_ops",
            QualityCallback.unpack(by_label["🖼 Проверка"]).action,
        )
        self.assertEqual(
            "reworks",
            QualityCallback.unpack(by_label["🛠 Доработка · 5"]).action,
        )
        self.assertEqual(
            "aijobs",
            QualityCallback.unpack(by_label["📋 История"]).action,
        )
        self.assertEqual(
            "refcompare_start",
            QualityCallback.unpack(by_label["🔎 Референс"]).action,
        )

    def test_ai_slash_fallbacks_have_button_entry_points(self) -> None:
        _, ai_markup = self._qwen_menu()
        _, operations_markup = build_quality_operations_menu(self.summary, None)
        actions = quality_actions(ai_markup) | quality_actions(operations_markup)
        command_to_button = {
            "quality": "quality_ops",
            "auditarchive": "menu",
            "qwen_calibration": "qcal",
            "qcalibration": "qcal",
            "analyze_set": "setreports",
            "qwen_set": "setreports",
            "compare_ref": "refcompare_start",
            "compare_reference": "refcompare_start",
            "rework": "reworks",
            "reworks": "reworks",
            "quality_rework": "reworks",
        }

        self.assertEqual(set(), set(command_to_button.values()) - actions)

    def test_quality_operations_keeps_only_worker_controls(self) -> None:
        text, markup = build_quality_operations_menu(self.summary, None)
        labels = {
            button.text
            for row in markup.inline_keyboard
            for button in row
        }
        expected = {
            "🖼 Новое фото",
            "📋 Отчёты",
            "❌ Ошибки",
            "🛠 Доработка",
            "🕘 Последние",
            "▶️ Запуск",
            "🔁 Повтор ошибок",
            "🔄 Обновить",
            "↩️ Qwen",
        }

        self.assertIn("управление фоновым worker", text)
        self.assertEqual(expected, labels)

    def test_each_primary_qwen_callback_has_a_handler(self) -> None:
        _, ai_markup = self._qwen_menu()
        _, operations_markup = build_quality_operations_menu(self.summary, None)
        actions = quality_actions(ai_markup) | quality_actions(operations_markup)

        self.assertEqual(set(), actions - registered_quality_actions())

    def test_every_literal_quality_callback_has_a_handler(self) -> None:
        self.assertEqual(
            set(),
            literal_quality_actions() - registered_quality_actions(),
        )

    def test_new_routers_are_connected_through_domain_bundles(self) -> None:
        quality_source = (
            ROOT / "velvet_bot/presentation/telegram/routers/quality_operations.py"
        ).read_text(encoding="utf-8")
        archive_source = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")

        self.assertIn("router.include_router(ai_jobs_router)", quality_source)
        self.assertIn("router.include_router(quality_operations_router)", quality_source)
        self.assertIn("register_quality_rework_entry(router)", quality_source)
        self.assertIn(
            "router.include_router(reference_comparison_help_router)",
            archive_source,
        )

    def test_each_interactive_qwen_flow_creates_a_job(self) -> None:
        quality_root = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/quality_operations_controllers"
        )
        paths = {
            "prompt_result": quality_root / "velvet_ai.py",
            "palette_composition": quality_root / "velvet_ai_visual.py",
            "velvet_formatting": quality_root / "velvet_ai_formatting.py",
            "quality_image": quality_root / "quality_operations.py",
            "reference_comparison": (
                ROOT
                / "velvet_bot/presentation/telegram/routers/references/comparison_help.py"
            ),
            "media_set_consistency": quality_root / "quality_set_ai.py",
        }
        for kind, path in paths.items():
            source = path.read_text(encoding="utf-8")
            self.assertIn("AIJobTracker.create", source, path.as_posix())
            self.assertIn(f'kind="{kind}"', source, path.as_posix())


if __name__ == "__main__":
    unittest.main()
