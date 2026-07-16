from __future__ import annotations

import asyncio
import json
import threading
import unittest
import urllib.request
from types import SimpleNamespace

from aiogram.types import InlineKeyboardMarkup

from velvet_bot.app.commands import (
    build_admin_commands,
    build_editor_commands,
    build_public_commands,
)
from velvet_bot.handlers.supervisor_control import (
    SupervisorCallback,
    SupervisorReplyMarkerFilter,
    _accepted_keyboard,
    _bot_keyboard,
    _codex_keyboard,
    _confirm_keyboard,
    _git_keyboard,
    _logs_keyboard,
    _main_keyboard,
    _task_keyboard,
)
from velvet_bot.owner_menu import (
    OwnerMenuCallback,
    build_owner_back_keyboard,
    build_owner_main_keyboard,
)
from velvet_supervisor.http_api import SupervisorHTTPServer


def _callback_values(keyboard: InlineKeyboardMarkup) -> list[str]:
    return [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def _assert_telegram_callback_lengths(
    case: unittest.TestCase,
    keyboard: InlineKeyboardMarkup,
) -> None:
    values = _callback_values(keyboard)
    case.assertTrue(values)
    for value in values:
        case.assertLessEqual(
            len(value.encode("utf-8")),
            64,
            msg=f"callback_data exceeds Telegram limit: {value}",
        )


class InlineManagementKeyboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tasks = [
            {
                "id": "a1b2c3d4e5f6",
                "status": "ready",
                "prompt": "Исправить навигацию кнопок и добавить тесты",
            },
            {
                "id": "001122334455",
                "status": "running",
                "prompt": "Проверить логи и обработку ошибок",
            },
        ]

    def test_all_owner_and_supervisor_callbacks_fit_telegram_limit(self) -> None:
        keyboards = [
            build_owner_main_keyboard(),
            build_owner_back_keyboard(),
            _main_keyboard(),
            _bot_keyboard(),
            _git_keyboard(),
            _logs_keyboard(50),
            _logs_keyboard(150),
            _logs_keyboard(500),
            _logs_keyboard(2000),
            _codex_keyboard(self.tasks),
            _task_keyboard({**self.tasks[0], "changed_files": ["a.py"]}),
            _task_keyboard(
                {
                    **self.tasks[0],
                    "status": "applied",
                    "pushed_at": None,
                }
            ),
            _confirm_keyboard(
                "codex.apply",
                "Применить",
                cancel_action="codex.open",
                task_id="a1b2c3d4e5f6",
            ),
            _accepted_keyboard(),
        ]
        for keyboard in keyboards:
            _assert_telegram_callback_lengths(self, keyboard)

    def test_supervisor_main_menu_reaches_every_section(self) -> None:
        values = set(_callback_values(_main_keyboard()))
        expected = {
            SupervisorCallback(action="bot.menu").pack(),
            SupervisorCallback(action="git.menu").pack(),
            SupervisorCallback(action="logs.menu").pack(),
            SupervisorCallback(action="codex.menu").pack(),
            SupervisorCallback(action="status").pack(),
            SupervisorCallback(action="close").pack(),
            OwnerMenuCallback(action="menu").pack(),
        }
        self.assertEqual(values, expected)

    def test_log_menu_has_all_sizes_download_and_back_paths(self) -> None:
        values = set(_callback_values(_logs_keyboard(150)))
        expected = {
            SupervisorCallback(action="logs.50").pack(),
            SupervisorCallback(action="logs.150").pack(),
            SupervisorCallback(action="logs.500").pack(),
            SupervisorCallback(action="logs.2000").pack(),
            SupervisorCallback(action="logs.file").pack(),
            SupervisorCallback(action="status").pack(),
            OwnerMenuCallback(action="menu").pack(),
        }
        self.assertEqual(values, expected)

    def test_codex_menu_opens_each_task_and_input_forms(self) -> None:
        values = set(_callback_values(_codex_keyboard(self.tasks)))
        self.assertIn(SupervisorCallback(action="codex.input").pack(), values)
        self.assertIn(SupervisorCallback(action="task.input").pack(), values)
        self.assertIn(SupervisorCallback(action="codex.menu").pack(), values)
        for task in self.tasks:
            self.assertIn(
                SupervisorCallback(
                    action="codex.open",
                    task_id=task["id"],
                ).pack(),
                values,
            )

    def test_ready_and_applied_task_buttons_are_status_specific(self) -> None:
        ready_values = set(
            _callback_values(
                _task_keyboard(
                    {
                        "id": "a1b2c3d4e5f6",
                        "status": "ready",
                        "changed_files": [],
                    }
                )
            )
        )
        self.assertIn(
            SupervisorCallback(
                action="codex.apply.ask",
                task_id="a1b2c3d4e5f6",
            ).pack(),
            ready_values,
        )
        self.assertIn(
            SupervisorCallback(
                action="codex.reject.ask",
                task_id="a1b2c3d4e5f6",
            ).pack(),
            ready_values,
        )

        applied_values = set(
            _callback_values(
                _task_keyboard(
                    {
                        "id": "a1b2c3d4e5f6",
                        "status": "applied",
                        "pushed_at": None,
                        "changed_files": [],
                    }
                )
            )
        )
        self.assertIn(
            SupervisorCallback(
                action="codex.push.ask",
                task_id="a1b2c3d4e5f6",
            ).pack(),
            applied_values,
        )

    def test_owner_menu_links_to_real_section_callback_prefixes(self) -> None:
        values = _callback_values(build_owner_main_keyboard())
        prefixes = {value.split(":", 1)[0] for value in values}
        self.assertTrue(
            {
                "pub",
                "adir",
                "sup",
                "sys",
                "quality",
                "bkp",
                "dash",
                "pubq",
                "own",
            }
            <= prefixes
        )

    def test_botfather_menu_is_compact_for_every_role(self) -> None:
        self.assertEqual(
            [item.command for item in build_public_commands()],
            ["start", "archive"],
        )
        self.assertEqual(
            [item.command for item in build_editor_commands()],
            ["start", "menu", "archive"],
        )
        self.assertEqual(
            [item.command for item in build_admin_commands()],
            ["start", "menu", "archive"],
        )


class SupervisorReplyMarkerTests(unittest.TestCase):
    def test_filter_only_accepts_supervisor_forms(self) -> None:
        filter_ = SupervisorReplyMarkerFilter()
        codex_message = SimpleNamespace(
            reply_to_message=SimpleNamespace(
                text="Введите задачу\nSUPERVISOR_INPUT:codex",
                caption=None,
            )
        )
        task_message = SimpleNamespace(
            reply_to_message=SimpleNamespace(
                text=None,
                caption="SUPERVISOR_INPUT:task",
            )
        )
        unrelated = SimpleNamespace(
            reply_to_message=SimpleNamespace(text="PUBLICATION_TEXT:12", caption=None)
        )

        self.assertEqual(
            asyncio.run(filter_(codex_message)),
            {"supervisor_input_kind": "codex"},
        )
        self.assertEqual(
            asyncio.run(filter_(task_message)),
            {"supervisor_input_kind": "task"},
        )
        self.assertFalse(asyncio.run(filter_(unrelated)))


class _LimitAwareCodex:
    def __init__(self) -> None:
        self.last_limit = None

    def list_tasks(self, *, limit: int = 20):
        self.last_limit = limit
        return [{"id": "task", "status": "ready"}]

    def get_dict(self, task_id: str):
        return {"id": task_id, "status": "ready"}


class _LimitAwareRuntime:
    def __init__(self, token: str) -> None:
        self.settings = SimpleNamespace(api_token=token)
        self.codex = _LimitAwareCodex()

    def status(self):
        return {"bot": {"running": True}}

    def log_tail(self, lines: int):
        return []


class SupervisorTaskListHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.token = "t" * 32
        self.runtime = _LimitAwareRuntime(self.token)
        self.server = SupervisorHTTPServer(
            ("127.0.0.1", 0),
            self.runtime,  # type: ignore[arg-type]
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_codex_list_limit_is_validated_and_forwarded(self) -> None:
        request = urllib.request.Request(
            self.base_url + "/v1/codex?limit=7",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(self.runtime.codex.last_limit, 7)
        self.assertEqual(payload["tasks"][0]["id"], "task")


if __name__ == "__main__":
    unittest.main()
