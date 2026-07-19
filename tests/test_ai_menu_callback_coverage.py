from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.handlers.quality_operations import build_quality_operations_menu
from velvet_bot.velvet_ai_ui import build_velvet_ai_menu

ROOT = Path(__file__).resolve().parents[1]


def quality_actions(markup) -> set[str]:
    actions: set[str] = set()
    for row in markup.inline_keyboard:
        for button in row:
            data = button.callback_data
            if data and data.startswith("quality:"):
                actions.add(data.split(":", 1)[1])
    return actions


def registered_quality_actions() -> set[str]:
    actions: set[str] = set()
    for path in (ROOT / "velvet_bot/handlers").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                text = ast.unparse(decorator)
                if "callback_query" not in text:
                    continue
                for value in ast.walk(decorator):
                    if (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and value.value.startswith("quality:")
                    ):
                        actions.add(value.value.split(":", 1)[1])
    return actions


def literal_quality_actions() -> set[str]:
    actions: set[str] = set()
    for path in (ROOT / "velvet_bot").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.startswith("quality:")
            ):
                actions.add(node.value.split(":", 1)[1])
    return actions


class AIMenuCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = SimpleNamespace(
            pending=0,
            processing=0,
            ready=0,
            errors=0,
            skipped=0,
            unreviewed=0,
            accepted=0,
            fix_required=0,
            clean=0,
            warnings=0,
            critical=0,
        )

    def test_ai_menu_contains_primary_operations(self) -> None:
        _, markup = build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
        )
        labels = {
            button.text
            for row in markup.inline_keyboard
            for button in row
        }
        expected = {
            "🔍 Проверить изображение",
            "🧬 Сравнить с референсом",
            "📝 Промт против результата",
            "🎨 Палитра и композиция",
            "🖋 Оформление Velvet Anatomy",
            "🧩 Проверить медиасет",
        }
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

    def test_new_routers_are_connected_through_domain_bundles(self) -> None:
        quality_source = (
            ROOT / "velvet_bot/presentation/telegram/routers/quality_operations.py"
        ).read_text(encoding="utf-8")
        archive_source = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")

        self.assertIn("router.include_router(ai_jobs_router)", quality_source)
        self.assertIn("router.include_router(quality_operations_router)", quality_source)
        self.assertIn(
            "router.include_router(reference_comparison_help_router)",
            archive_source,
        )

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
