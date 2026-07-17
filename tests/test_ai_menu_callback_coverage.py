from __future__ import annotations

import re
import unittest
from pathlib import Path

from velvet_bot.ai_quality import AIQualitySummary
from velvet_bot.handlers.quality_operations import build_quality_operations_menu
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


def registered_quality_actions() -> set[str]:
    actions: set[str] = set()
    for path in (ROOT / "velvet_bot/handlers").glob("*.py"):
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

    def test_primary_menu_routes_to_operations_history_and_reference_form(self) -> None:
        _, markup = build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
        )
        by_label = {
            button.text: button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }

        self.assertEqual(
            "quality_ops",
            QualityCallback.unpack(by_label["🧠 Проверка качества"]).action,
        )
        self.assertEqual(
            "aijobs",
            QualityCallback.unpack(by_label["📋 История AI-заданий"]).action,
        )
        self.assertEqual(
            "refcompare_start",
            QualityCallback.unpack(by_label["🔎 Сравнение с референсом"]).action,
        )

    def test_quality_operations_restores_expected_controls(self) -> None:
        text, markup = build_quality_operations_menu(self.summary, None)
        labels = {
            button.text
            for row in markup.inline_keyboard
            for button in row
        }
        expected = {
            "🖼 Проверить новое изображение",
            "📋 Отчёты Qwen",
            "❌ Очередь ошибок",
            "🧬 Поиск дублей",
            "🎞 Медиасеты",
            "🧠 Целостность сетов",
            "🕘 Проверить последние файлы",
            "▶️ Запустить проверку",
            "🔄 Повторить ошибки",
        }

        self.assertIn("Управление фоновыми проверками", text)
        self.assertTrue(expected.issubset(labels))

    def test_each_primary_quality_callback_has_a_handler(self) -> None:
        _, ai_markup = build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
        )
        _, operations_markup = build_quality_operations_menu(self.summary, None)
        actions = quality_actions(ai_markup) | quality_actions(operations_markup)

        self.assertEqual(set(), actions - registered_quality_actions())

    def test_every_literal_quality_callback_has_a_handler(self) -> None:
        self.assertEqual(
            set(),
            literal_quality_actions() - registered_quality_actions(),
        )

    def test_new_routers_are_connected(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/router.py"
        ).read_text(encoding="utf-8")

        self.assertIn("root.include_router(ai_jobs_router)", source)
        self.assertIn("root.include_router(quality_operations_router)", source)
        self.assertIn("root.include_router(reference_comparison_help_router)", source)

    def test_each_interactive_ai_flow_creates_a_job(self) -> None:
        paths = {
            "prompt_result": ROOT / "velvet_bot/handlers/velvet_ai.py",
            "palette_composition": ROOT / "velvet_bot/handlers/velvet_ai_visual.py",
            "velvet_formatting": ROOT / "velvet_bot/handlers/velvet_ai_formatting.py",
            "quality_image": ROOT / "velvet_bot/handlers/quality_operations.py",
            "reference_comparison": ROOT / "velvet_bot/handlers/reference_comparison_help.py",
            "media_set_consistency": ROOT / "velvet_bot/handlers/quality_set_ai.py",
        }
        for kind, path in paths.items():
            source = path.read_text(encoding="utf-8")
            self.assertIn("AIJobTracker.create", source, path.as_posix())
            self.assertIn(f'kind="{kind}"', source, path.as_posix())


if __name__ == "__main__":
    unittest.main()
