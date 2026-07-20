from __future__ import annotations

import unittest
from pathlib import Path


RETIRED_SUPERVISOR_ALIASES = (
    "supervisor_control",
    "supervisor_status",
    "supervisor_process",
    "supervisor_git",
    "supervisor_logs",
    "supervisor_console",
    "supervisor_self",
    "supervisor_codex",
)
SUPERVISOR_CANONICAL_MODULES = (
    "velvet_bot.presentation.telegram.routers.supervisor.control",
    "velvet_bot.presentation.telegram.routers.supervisor.status",
    "velvet_bot.presentation.telegram.routers.supervisor.process",
    "velvet_bot.presentation.telegram.routers.supervisor.git",
    "velvet_bot.presentation.telegram.routers.supervisor.logs",
    "velvet_bot.presentation.telegram.routers.supervisor.console",
    "velvet_bot.presentation.telegram.routers.supervisor.self_control",
    "velvet_bot.presentation.telegram.routers.supervisor.codex",
)
LEGACY_SUPERVISOR_PREFIX = ".".join(("velvet_bot", "handlers", "supervisor"))
SYSTEM_ALIAS_NAME = "system_center"
SYSTEM_CANONICAL = "velvet_bot.presentation.telegram.routers.system"


class P3CSupervisorSystemPresentationTests(unittest.TestCase):
    def test_supervisor_alias_files_are_retired(self) -> None:
        for name in RETIRED_SUPERVISOR_ALIASES:
            with self.subTest(alias=name):
                path = Path("velvet_bot/handlers", f"{name}.py")
                self.assertFalse(path.exists())

    def test_system_alias_is_retired(self) -> None:
        path = Path("velvet_bot/handlers", f"{SYSTEM_ALIAS_NAME}.py")
        self.assertFalse(path.exists())

    def test_canonical_controllers_own_router_implementations(self) -> None:
        for canonical_name in (*SUPERVISOR_CANONICAL_MODULES, SYSTEM_CANONICAL):
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
            self.assertNotIn(LEGACY_SUPERVISOR_PREFIX, text)
        self.assertIn(
            "velvet_bot.presentation.telegram.routers.supervisor.control",
            source,
        )
        self.assertIn(SYSTEM_CANONICAL, source)

    def test_supervisor_control_composes_focused_controllers(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/supervisor/control.py"
        ).read_text(encoding="utf-8")
        for router_name in (
            "status_router",
            "process_router",
            "git_router",
            "logs_router",
            "console_router",
            "self_router",
            "codex_router",
        ):
            with self.subTest(router=router_name):
                self.assertIn(f"router.include_router({router_name})", source)


if __name__ == "__main__":
    unittest.main()
