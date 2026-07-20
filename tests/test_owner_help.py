from __future__ import annotations

import ast
import unittest
from pathlib import Path

from velvet_bot.app.commands import (
    build_admin_commands,
    build_editor_commands,
    build_public_commands,
)
from velvet_bot.core.access import (
    MODERATOR_COMMANDS,
    MODERATOR_TAG_COMMANDS,
    is_public_command_text,
)
from velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_help import (
    OWNER_HELP_COMMANDS,
    build_owner_help_pages,
)


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOTS = (ROOT / "velvet_bot", ROOT / "velvet_supervisor")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}".strip(".")
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _literal_strings(call: ast.Call) -> set[str]:
    return {
        argument.value
        for argument in call.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    }


def _commands_from_filter(call: ast.Call) -> set[str]:
    name = _call_name(call.func)
    if name.endswith("CommandStart"):
        return {"start"}
    if name.endswith("Command"):
        return _literal_strings(call)
    return set()


def _registered_commands() -> set[str]:
    commands: set[str] = set()
    for root in PYTHON_ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node.func)
                if name.endswith("router.message"):
                    for argument in node.args:
                        if isinstance(argument, ast.Call):
                            commands.update(_commands_from_filter(argument))
                elif name.endswith("message.register"):
                    for argument in node.args:
                        if isinstance(argument, ast.Call):
                            commands.update(_commands_from_filter(argument))
    return commands


def _menu_commands(builder) -> set[str]:
    return {item.command for item in builder()}


class OwnerHelpTests(unittest.TestCase):
    def test_help_is_owner_only_and_keeps_botfather_menus_compact(self) -> None:
        self.assertNotIn("help", _menu_commands(build_admin_commands))
        self.assertNotIn("help", _menu_commands(build_editor_commands))
        self.assertNotIn("help", _menu_commands(build_public_commands))
        self.assertFalse(is_public_command_text("/help"))
        self.assertNotIn("help", MODERATOR_COMMANDS | MODERATOR_TAG_COMMANDS)

    def test_help_lists_every_registered_slash_command(self) -> None:
        self.assertEqual(_registered_commands(), set(OWNER_HELP_COMMANDS))

    def test_help_pages_fit_telegram_and_render_every_command(self) -> None:
        pages = build_owner_help_pages()
        rendered = "\n".join(pages)
        self.assertTrue(pages)
        self.assertTrue(all(len(page) <= 4096 for page in pages))
        for command in OWNER_HELP_COMMANDS:
            self.assertIn(f"<code>/{command}</code>", rendered)


if __name__ == "__main__":
    unittest.main()
