from __future__ import annotations

import ast
import unittest
from pathlib import Path

from aiogram.types import CallbackQuery, User

from velvet_bot.core.access import (
    MODERATOR_CALLBACK_ACTIONS,
    MODERATOR_CALLBACK_PREFIXES,
    MODERATOR_COMMANDS,
    OWNER_ONLY_COMMANDS,
    PUBLIC_CALLBACK_ACTIONS,
    PUBLIC_CALLBACK_PREFIX,
    PUBLIC_COMMANDS,
)
from velvet_bot.presentation.telegram.middleware.access import (
    is_moderator_callback,
    is_public_callback,
)
from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback


MODERATOR_ID = 900000001
MODERATOR_IDS = frozenset({MODERATOR_ID})

SUPERVISOR_CONTROLLERS = {
    "velvet_bot/presentation/telegram/routers/supervisor/status.py": {
        "supervisor",
        "status",
    },
    "velvet_bot/presentation/telegram/routers/supervisor/process.py": {"restart"},
    "velvet_bot/presentation/telegram/routers/supervisor/git.py": {
        "update",
        "rollback",
    },
    "velvet_bot/presentation/telegram/routers/supervisor/logs.py": {"logs"},
    "velvet_bot/presentation/telegram/routers/supervisor/console.py": {
        "console",
        "supervisor_console",
    },
    "velvet_bot/presentation/telegram/routers/supervisor/self_control.py": {
        "supervisor_self"
    },
    "velvet_bot/presentation/telegram/routers/supervisor/codex.py": {
        "codex",
        "codex_status",
    },
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


def _callback(user: User, data: str, *, callback_id: str) -> CallbackQuery:
    return CallbackQuery(
        id=callback_id,
        from_user=user,
        chat_instance="test",
        data=data,
    )


class AccessBoundaryTests(unittest.TestCase):
    def test_public_access_includes_archive_engagement(self) -> None:
        self.assertEqual(PUBLIC_COMMANDS, {"start", "archive", "gallery"})
        self.assertEqual(PUBLIC_CALLBACK_PREFIX, "pub:")
        self.assertEqual(
            PUBLIC_CALLBACK_ACTIONS,
            {
                "categories",
                "universes",
                "stories",
                "menu",
                "open",
                "show",
                "noop",
                "close",
                "back",
                "like",
                "sub",
            },
        )
        self.assertNotIn("menu", PUBLIC_COMMANDS)
        self.assertIn("like", PUBLIC_CALLBACK_ACTIONS)
        self.assertIn("sub", PUBLIC_CALLBACK_ACTIONS)
        self.assertNotIn("download", PUBLIC_CALLBACK_ACTIONS)

    def test_configured_moderator_has_narrow_editor_permissions(self) -> None:
        self.assertEqual(MODERATOR_COMMANDS, {"characters", "prompt", "setprompt"})
        self.assertEqual(
            MODERATOR_CALLBACK_PREFIXES,
            ("adir:", "astory:", "arc:", "pub:"),
        )
        self.assertEqual(
            set(MODERATOR_CALLBACK_ACTIONS),
            {"adir", "astory", "arc", "pub"},
        )
        self.assertEqual(MODERATOR_CALLBACK_ACTIONS["pub"], {"download"})

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
        moderator = User(id=MODERATOR_ID, is_bot=False, first_name="Moderator")
        supervisor_callback = _callback(
            moderator,
            SupervisorCallback(action="status").pack(),
            callback_id="supervisor",
        )
        moderator_callback = _callback(
            moderator,
            "adir:profile:0",
            callback_id="moderator",
        )
        public_callback = _callback(
            moderator,
            "pub:categories:0",
            callback_id="public",
        )
        self.assertFalse(is_public_callback(supervisor_callback))
        self.assertFalse(
            is_moderator_callback(supervisor_callback, MODERATOR_IDS)
        )
        self.assertTrue(is_moderator_callback(moderator_callback, MODERATOR_IDS))
        self.assertTrue(is_public_callback(public_callback))

    def test_likes_and_subscriptions_are_public_but_management_is_not(self) -> None:
        stranger = User(id=11, is_bot=False, first_name="Viewer")
        for action in ("like", "sub"):
            with self.subTest(action=action):
                self.assertTrue(
                    is_public_callback(
                        _callback(
                            stranger,
                            f"pub:{action}:1:0:2",
                            callback_id=action,
                        )
                    )
                )
        for action in ("download", "pcat", "puni", "purge"):
            with self.subTest(action=action):
                self.assertFalse(
                    is_public_callback(
                        _callback(
                            stranger,
                            f"pub:{action}:1:0:2",
                            callback_id=action,
                        )
                    )
                )

    def test_unknown_actions_do_not_inherit_moderator_access(self) -> None:
        moderator = User(id=MODERATOR_ID, is_bot=False, first_name="Moderator")
        for data in (
            "adir:owner_settings:0",
            "astory:delete_catalog:0",
            "arc:purge_all:0",
            "pub:purge:1:0:2",
            "sup:status:",
        ):
            with self.subTest(data=data):
                self.assertFalse(
                    is_moderator_callback(
                        _callback(moderator, data, callback_id=data),
                        MODERATOR_IDS,
                    )
                )

    def test_current_moderator_archive_actions_remain_available(self) -> None:
        moderator = User(id=MODERATOR_ID, is_bot=False, first_name="Moderator")
        for action in (
            "open",
            "show",
            "spoiler",
            "prompt",
            "promptremove",
            "del",
            "delok",
            "delno",
            "close",
        ):
            with self.subTest(action=action):
                self.assertTrue(
                    is_moderator_callback(
                        _callback(
                            moderator,
                            f"arc:{action}:1:0:2",
                            callback_id=action,
                        ),
                        MODERATOR_IDS,
                    )
                )
        self.assertTrue(
            is_moderator_callback(
                _callback(
                    moderator,
                    "pub:download:1:0:2",
                    callback_id="download",
                ),
                MODERATOR_IDS,
            )
        )


class SupervisorArchitectureTests(unittest.TestCase):
    def test_legacy_supervisor_modules_are_aliases_without_handlers(self) -> None:
        aliases = {
            "supervisor_control.py": "routers.supervisor.control",
            "supervisor_status.py": "routers.supervisor.status",
            "supervisor_process.py": "routers.supervisor.process",
            "supervisor_git.py": "routers.supervisor.git",
            "supervisor_logs.py": "routers.supervisor.logs",
            "supervisor_console.py": "routers.supervisor.console",
            "supervisor_self.py": "routers.supervisor.self_control",
            "supervisor_codex.py": "routers.supervisor.codex",
        }
        for filename, target in aliases.items():
            with self.subTest(filename=filename):
                path = Path("velvet_bot/handlers") / filename
                source = path.read_text(encoding="utf-8")
                self.assertEqual(_commands(str(path)), set())
                self.assertIn("P3_COMPAT_MODULE_ALIAS", source)
                self.assertIn(target, source)
                self.assertNotIn("@router.", source)

    def test_system_controller_is_canonical_and_alias_is_absent(self) -> None:
        canonical = Path("velvet_bot/presentation/telegram/routers/system.py")
        self.assertTrue(canonical.exists())
        self.assertIn("router = Router(name=__name__)", canonical.read_text(encoding="utf-8"))
        self.assertFalse((Path("velvet_bot/handlers") / "system_center.py").exists())

    def test_each_controller_owns_only_its_commands(self) -> None:
        for path, expected in SUPERVISOR_CONTROLLERS.items():
            with self.subTest(path=path):
                self.assertEqual(_commands(path), expected)

    def test_callback_contract_has_one_prefix_definition(self) -> None:
        contract = Path(
            "velvet_bot/presentation/telegram/supervisor/contract.py"
        ).read_text(encoding="utf-8")
        control = Path(
            "velvet_bot/presentation/telegram/routers/supervisor/control.py"
        ).read_text(encoding="utf-8")
        facade = Path("velvet_bot/handlers/supervisor_control.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('prefix="sup"', contract)
        self.assertNotIn('prefix="sup"', control)
        self.assertNotIn('prefix="sup"', facade)
        self.assertNotIn("class SupervisorCallback", control)
        self.assertNotIn("class SupervisorCallback", facade)


if __name__ == "__main__":
    unittest.main()
