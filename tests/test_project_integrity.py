from __future__ import annotations

import ast
import re
import unittest
from collections import defaultdict
from pathlib import Path


PYTHON_ROOTS = (Path("velvet_bot"), Path("velvet_supervisor"))
LEGACY_DUPLICATE_MIGRATIONS = {
    "003": {"003_character_references.sql", "003_public_archive.sql"},
}
ALLOWED_DUPLICATE_COMMAND_ROUTES = {
    "characters",
    "prompt",
    "setprompt",
    "publish",
    "publishing",
    "publications",
    "checkpost",
    "refs",
    "ref",
    "refadd",
}
PANEL_COMMANDS = {
    "admin",
    "menu",
    "system",
    "health",
    "version",
    "diag",
    "diagnostics",
    "analytics",
    "analyticsmenu",
    "channelstats",
    "stats",
    "promptstats",
    "characterstats",
    "backup",
    "quality",
    "auditarchive",
    "qwen_calibration",
    "qcalibration",
    "publish",
    "publishing",
    "publications",
    "characters",
    "supervisor",
    "status",
    "logs",
    "restart",
    "update",
    "rollback",
    "codex",
    "codex_status",
    "console",
    "supervisor_console",
    "supervisor_self",
}
FORM_COMMANDS = {
    "create",
    "crete",
    "topic",
    "character",
    "category",
    "cat",
    "universe",
    "world",
    "series",
    "story",
    "stories",
    "storylist",
    "storyadd",
    "prompt",
    "setprompt",
    "refadd",
    "refs",
    "ref",
    "refdel",
    "compare_ref",
    "compare_reference",
    "analyze_set",
    "qwen_set",
    "aliasadd",
    "tagadd",
    "aliases",
    "tags",
    "aliasdel",
    "tagdel",
    "tagstats",
    "hashtagstats",
    "trackdiscussion",
    "discussionstats",
}
CONTEXT_COMMANDS = {
    "save",
    "save18",
    "checkpost",
    "importchannel",
    "importdiscussion",
    "watermark",
}
DIRECT_COMMANDS = {
    "savecancel",
    "refdone",
    "refcancel",
    "aliasreindex",
    "tagreindex",
    "test_error_alert",
    "diag_export",
    "workspace_grant",
    "workspace_revoke",
    "workspace_module",
}
PUBLIC_COMMANDS = {"archive", "gallery"}


def _python_files() -> list[Path]:
    return sorted(path for root in PYTHON_ROOTS for path in root.rglob("*.py"))


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}".strip(".")
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _literal_strings(call: ast.Call) -> list[str]:
    return [
        argument.value
        for argument in call.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    ]


def _command_routes() -> dict[str, list[str]]:
    routes: dict[str, list[str]] = defaultdict(list)
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    if not _call_name(decorator.func).endswith("router.message"):
                        continue
                    for argument in decorator.args:
                        if not isinstance(argument, ast.Call):
                            continue
                        if not _call_name(argument.func).endswith("Command"):
                            continue
                        for command in _literal_strings(argument):
                            routes[command].append(
                                f"{path}:{node.lineno}:{node.name}"
                            )
                continue

            if not isinstance(node, ast.Call):
                continue
            if not _call_name(node.func).endswith("router.message.register"):
                continue
            if not node.args:
                continue
            handler_name = _call_name(node.args[0]) or "<dynamic>"
            for argument in node.args[1:]:
                if not isinstance(argument, ast.Call):
                    continue
                if not _call_name(argument.func).endswith("Command"):
                    continue
                for command in _literal_strings(argument):
                    routes[command].append(
                        f"{path}:{node.lineno}:{handler_name}"
                    )
    return routes


def _callback_prefixes() -> dict[str, list[str]]:
    prefixes: dict[str, list[str]] = defaultdict(list)
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(_call_name(base).endswith("CallbackData") for base in node.bases):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "prefix"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    prefixes[keyword.value.value].append(f"{path}:{node.name}")
    return prefixes


class ProjectIntegrityTests(unittest.TestCase):
    def test_every_python_source_parses(self) -> None:
        for path in _python_files():
            with self.subTest(path=path):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_callback_prefixes_are_unique(self) -> None:
        duplicates = {
            prefix: owners
            for prefix, owners in _callback_prefixes().items()
            if len(owners) > 1
        }
        self.assertEqual(duplicates, {})

    def test_every_real_command_has_an_explicit_ui_or_reserve_route(self) -> None:
        actual = set(_command_routes())
        covered = (
            PANEL_COMMANDS
            | FORM_COMMANDS
            | CONTEXT_COMMANDS
            | DIRECT_COMMANDS
            | PUBLIC_COMMANDS
        )
        self.assertEqual(actual, covered)

    def test_only_filter_disambiguated_commands_have_multiple_handlers(self) -> None:
        duplicate_routes = {
            command
            for command, routes in _command_routes().items()
            if len(routes) > 1
        }
        self.assertEqual(duplicate_routes, ALLOWED_DUPLICATE_COMMAND_ROUTES)

    def test_menu_command_has_one_owner_meaning(self) -> None:
        routes = _command_routes().get("menu", [])
        self.assertEqual(len(routes), 1)
        self.assertIn(
            "presentation/telegram/routers/core_operations_controllers/owner_menu.py",
            routes[0].replace("\\", "/"),
        )

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
            Path(
                "velvet_bot/presentation/telegram/routers/"
                "core_operations_controllers/owner_actions.py"
            ),
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
