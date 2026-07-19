from __future__ import annotations

import ast
import re
import unittest
from collections import defaultdict
from pathlib import Path

from velvet_bot.presentation.telegram.router import get_root_router


LEGACY_DUPLICATE_MIGRATIONS = {
    "003": {"003_channel_analytics.sql", "003_public_archive.sql"}
}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _command_routes() -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for path in Path("velvet_bot").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not _dotted(decorator.func).endswith("message"):
                    continue
                for argument in decorator.args:
                    if not isinstance(argument, ast.Call):
                        continue
                    if not _dotted(argument.func).endswith("Command"):
                        continue
                    for value in argument.args:
                        if isinstance(value, ast.Constant) and isinstance(value.value, str):
                            result[value.value].append(str(path))
    return result


class ProjectIntegrityTests(unittest.TestCase):
    def test_python_files_parse(self) -> None:
        for path in Path("velvet_bot").rglob("*.py"):
            with self.subTest(path=path):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_root_router_is_constructible(self) -> None:
        self.assertIsNotNone(get_root_router())

    def test_menu_command_has_one_owner_route(self) -> None:
        routes = _command_routes().get("menu", [])
        self.assertEqual(len(routes), 1)
        self.assertIn("handlers/owner_menu.py", routes[0].replace("\\", "/"))

    def test_migration_numbers_are_unambiguous_except_legacy_pair(self) -> None:
        by_number: dict[str, set[str]] = defaultdict(set)
        for path in sorted(Path("migrations").glob("*.sql")):
            match = re.match(r"(\d+)_", path.name)
            if match:
                by_number[match.group(1)].add(path.name)
        duplicates = {
            number: names for number, names in by_number.items() if len(names) > 1
        }
        self.assertEqual(duplicates, LEGACY_DUPLICATE_MIGRATIONS)

    def test_owner_callbacks_are_typed_and_not_split_across_fix_router(self) -> None:
        self.assertFalse(Path("velvet_bot/handlers/owner_action_callback_fix.py").exists())
        for path in (
            Path("velvet_bot/owner_menu.py"),
            Path("velvet_bot/handlers/owner_actions.py"),
        ):
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r'callback_data\s*=\s*["\'](?:own|oact):')

    def test_owner_forms_precede_private_and_topic_catch_all_handlers(self) -> None:
        root_source = Path("velvet_bot/presentation/telegram/router.py").read_text(
            encoding="utf-8"
        )
        archive_source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")

        core_index = root_source.index("root.include_router(core_operations_router)")
        archive_bundle_index = root_source.index(
            "root.include_router(archive_and_public_router)"
        )
        publication_index = archive_source.index(
            "router.include_router(publication_center_router)"
        )
        archive_index = archive_source.index("router.include_router(archive_router)")
        self.assertLess(core_index, archive_bundle_index)
        self.assertLess(publication_index, archive_index)


if __name__ == "__main__":
    unittest.main()
