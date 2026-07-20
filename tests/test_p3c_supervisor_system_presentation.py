from __future__ import annotations

import importlib
import unittest
from pathlib import Path


SUPERVISOR_ALIASES = {
    "velvet_bot.handlers.supervisor_control": (
        "velvet_bot.presentation.telegram.routers.supervisor.control"
    ),
    "velvet_bot.handlers.supervisor_status": (
        "velvet_bot.presentation.telegram.routers.supervisor.status"
    ),
    "velvet_bot.handlers.supervisor_process": (
        "velvet_bot.presentation.telegram.routers.supervisor.process"
    ),
    "velvet_bot.handlers.supervisor_git": (
        "velvet_bot.presentation.telegram.routers.supervisor.git"
    ),
    "velvet_bot.handlers.supervisor_logs": (
        "velvet_bot.presentation.telegram.routers.supervisor.logs"
    ),
    "velvet_bot.handlers.supervisor_console": (
        "velvet_bot.presentation.telegram.routers.supervisor.console"
    ),
    "velvet_bot.handlers.supervisor_self": (
        "velvet_bot.presentation.telegram.routers.supervisor.self_control"
    ),
    "velvet_bot.handlers.supervisor_codex": (
        "velvet_bot.presentation.telegram.routers.supervisor.codex"
    ),
}
SYSTEM_ALIAS = "velvet_bot.handlers.system_center"
SYSTEM_CANONICAL = "velvet_bot.presentation.telegram.routers.system"


class P3CSupervisorSystemPresentationTests(unittest.TestCase):
    def test_supervisor_legacy_imports_resolve_to_canonical_module_objects(self) -> None:
        for legacy_name, canonical_name in SUPERVISOR_ALIASES.items():
            with self.subTest(legacy=legacy_name):
                legacy = importlib.import_module(legacy_name)
                canonical = importlib.import_module(canonical_name)
                self.assertIs(legacy, canonical)

    def test_supervisor_legacy_files_are_only_module_aliases(self) -> None:
        for legacy_name, canonical_name in SUPERVISOR_ALIASES.items():
            with self.subTest(legacy=legacy_name):
                path = Path(*legacy_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("P3_COMPAT_MODULE_ALIAS", source)
                self.assertIn(canonical_name, source)
                self.assertNotIn("@router.", source)
                self.assertLessEqual(len(source.splitlines()), 8)

    def test_system_alias_is_retired(self) -> None:
        path = Path(*SYSTEM_ALIAS.split(".")).with_suffix(".py")
        self.assertFalse(path.exists())

    def test_canonical_controllers_own_router_implementations(self) -> None:
        for canonical_name in (*SUPERVISOR_ALIASES.values(), SYSTEM_CANONICAL):
            with self.subTest(canonical=canonical_name):
                path = Path(*canonical_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("router = Router(name=__name__)", source)

    def test_active_composition_uses_canonical_paths(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/core_operations.py"
        ).read_text(encoding="utf-8")
        owner_menu = Path("velvet_bot/owner_menu.py").read_text(encoding="utf-8")
        for text in (source, owner_menu):
            self.assertNotIn("velvet_bot.handlers.supervisor_control", text)
            self.assertNotIn(SYSTEM_ALIAS, text)
        self.assertIn(
            "velvet_bot.presentation.telegram.routers.supervisor.control",
            source,
        )
        self.assertIn(SYSTEM_CANONICAL, source)


if __name__ == "__main__":
    unittest.main()
