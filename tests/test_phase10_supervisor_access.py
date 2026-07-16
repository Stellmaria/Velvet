from __future__ import annotations

import ast
import unittest
from pathlib import Path

from aiogram.types import CallbackQuery, User

from velvet_bot.core.access import (
    MODERATOR_CALLBACK_PREFIXES,
    MODERATOR_COMMANDS,
    MODERATOR_USER_IDS,
    OWNER_ONLY_COMMANDS,
    PUBLIC_CALLBACK_PREFIX,
    PUBLIC_COMMANDS,
)
from velvet_bot.presentation.telegram.middleware.access import (
    is_moderator_callback,
    is_public_callback,
)
from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback


SUPERVISOR_CONTROLLERS = {
    "velvet_bot/handlers/supervisor_status.py": {"supervisor", "status"},
    "velvet_bot/handlers/supervisor_process.py": {"restart"},
    "velvet_bot/handlers/supervisor_git.py": {"update", "rollback"},
    "velvet_bot/handlers/supervisor_logs.py": {"logs"},
    "velvet_bot/handlers/supervisor_codex.py": {"codex", "codex_status"},
}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}".strip(".")
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _commands(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=path)
    commands: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
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
                commands.update(
                    value.value
                    for value in argument.args
                    if isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                )
    return commands


class AccessBoundaryTests(unittest.TestCase):
    def test_public_access_is_archive_viewing_only(self) -> None:
        self.assertEqual(PUBLIC_COMMANDS, {"start", "archive", "gallery"})
        self.assertEqual(PUBLIC_CALLBACK_PREFIX, "pub:")
        self.assertNotIn("menu", PUBLIC_COMMANDS)

    def test_single_moderator_has_narrow_editor_permissions(self) -> None:
        self.assertEqual(MODERATOR_USER_IDS, {8179531132})
        self.assertEqual(MODERATOR_COMMANDS, {"characters", "prompt", "setprompt"})
        self.assertEqual(MODERATOR_CALLBACK_PREFIXES, ("adir:", "astory:", "arc:"))

    def test_owner_system_commands_do_not_overlap_other_roles(self) -> None:
        self.assertTrue(PUBLIC_COMMANDS.isdisjoint(OWNER_ONLY_COMMANDS))
        self.assertTrue(MODERATOR_COMMANDS.isdisjoint(OWNER_ONLY_COMMANDS))
        self.assertTrue(
            {
                "menu",
                "system",
                "backup",
                "publish",
                "supervisor",
                "status",
                "logs",
                "restart",
                "update",
                "rollback",
                "codex",
                "codex_status",
            }.issubset(OWNER_ONLY_COMMANDS)
        )

    def test_supervisor_callback_is_owner_only(self) -> None:
        moderator = User(id=8179531132, is_bot=False, first_name="Moderator")
        supervisor_callback = CallbackQuery(
            id="supervisor",
            from_user=moderator,
            chat_instance="test",
            data=SupervisorCallback(action="status").pack(),
        )
        moderator_callback = CallbackQuery(
            id="moderator",
            from_user=moderator,
            chat_instance="test",
            data="adir:profile:0",
        )
        public_callback = CallbackQuery(
            id="public",
            from_user=moderator,
            chat_instance="test",
            data="pub:archive:0",
        )
        self.assertFalse(is_public_callback(supervisor_callback))
        self.assertFalse(is_moderator_callback(supervisor_callback))
        self.assertTrue(is_moderator_callback(moderator_callback))
        self.assertTrue(is_public_callback(public_callback))


class SupervisorArchitectureTests(unittest.TestCase):
    def test_facade_contains_no_command_handlers(self) -> None:
        path = Path("velvet_bot/handlers/supervisor_control.py")
        source = path.read_text(encoding="utf-8")
        self.assertEqual(_commands(str(path)), set())
        self.assertLess(len(source.splitlines()), 100)
        for module in ("status", "process", "git", "logs", "codex"):
            self.assertIn(f"supervisor_{module}", source)

    def test_each_controller_owns_only_its_commands(self) -> None:
        for path, expected in SUPERVISOR_CONTROLLERS.items():
            with self.subTest(path=path):
                self.assertEqual(_commands(path), expected)

    def test_callback_contract_has_one_prefix_definition(self) -> None:
        contract = Path(
            "velvet_bot/presentation/telegram/supervisor/contract.py"
        ).read_text(encoding="utf-8")
        facade = Path("velvet_bot/handlers/supervisor_control.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('prefix="sup"', contract)
        self.assertNotIn('prefix="sup"', facade)
        self.assertNotIn("class SupervisorCallback", facade)


if __name__ == "__main__":
    unittest.main()
