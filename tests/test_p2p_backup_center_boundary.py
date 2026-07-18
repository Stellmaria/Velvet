from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.backup_center as module


class FakeCallback:
    def __init__(self) -> None:
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.from_user = SimpleNamespace(id=17)
        self.message = object()

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))


class FakeBadRequest(Exception):
    pass


class BackupCenterBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_show_menu = module._show_menu
        self.original_edit = module._edit
        self.original_bad_request = module.TelegramBadRequest

    def tearDown(self) -> None:
        module._show_menu = self.original_show_menu
        module._edit = self.original_edit
        module.TelegramBadRequest = self.original_bad_request

    async def test_expected_backup_error_is_rendered_and_swallowed(self) -> None:
        callback = FakeCallback()
        rendered: list[str] = []

        async def fail_menu(callback, service, database) -> None:
            raise module.BackupError("pg_dump unavailable")

        async def record_edit(callback, text, keyboard) -> None:
            rendered.append(text)

        module._show_menu = fail_menu
        module._edit = record_edit

        await module.handle_backup_callback(
            callback,
            SimpleNamespace(action="menu"),
            object(),
            object(),
        )

        self.assertEqual(len(rendered), 1)
        self.assertIn("pg_dump unavailable", rendered[0])
        self.assertEqual(len(callback.answers), 1)

    async def test_unexpected_error_remains_original_when_render_fails(self) -> None:
        callback = FakeCallback()
        original = RuntimeError("database connection lost")
        rendered: list[str] = []

        async def fail_menu(callback, service, database) -> None:
            raise original

        async def fail_edit(callback, text, keyboard) -> None:
            rendered.append(text)
            raise FakeBadRequest("message unavailable")

        module._show_menu = fail_menu
        module._edit = fail_edit
        module.TelegramBadRequest = FakeBadRequest

        with self.assertRaises(RuntimeError) as caught:
            await module.handle_backup_callback(
                callback,
                SimpleNamespace(action="menu"),
                object(),
                object(),
            )

        self.assertIs(caught.exception, original)
        self.assertEqual(len(rendered), 1)
        self.assertIn("database connection lost", rendered[0])
        self.assertEqual(callback.answers, [])

    async def test_cancellation_is_not_rendered_or_swallowed(self) -> None:
        callback = FakeCallback()
        edits: list[str] = []

        async def cancel_menu(callback, service, database) -> None:
            raise asyncio.CancelledError

        async def record_edit(callback, text, keyboard) -> None:
            edits.append(text)

        module._show_menu = cancel_menu
        module._edit = record_edit

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_backup_callback(
                callback,
                SimpleNamespace(action="menu"),
                object(),
                object(),
            )

        self.assertEqual(edits, [])
        self.assertEqual(callback.answers, [])


if __name__ == "__main__":
    unittest.main()
