from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.public_manager as module


class FakeCallback:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=17)
        self.message = object()
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.answer_error: BaseException | None = None

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))
        if self.answer_error is not None:
            raise self.answer_error


class PublicManagerDownloadBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_access = module.has_public_manager_access
        self.original_get_page = module.get_archive_page
        self.original_send = module._send_as_document

        module.has_public_manager_access = lambda user, policy: True
        self.page = SimpleNamespace(
            media=SimpleNamespace(id=11, display_file_name="image.png"),
            character=SimpleNamespace(id=7),
            offset=0,
        )

        async def load_page(database, character_id, offset):
            return self.page

        module.get_archive_page = load_page
        self.data = SimpleNamespace(
            action="download",
            character_id=7,
            offset=0,
            media_id=11,
        )

    def tearDown(self) -> None:
        module.has_public_manager_access = self.original_access
        module.get_archive_page = self.original_get_page
        module._send_as_document = self.original_send

    async def test_download_failure_is_answered(self) -> None:
        async def fail_send(*args, **kwargs):
            raise RuntimeError("download failed")

        module._send_as_document = fail_send
        callback = FakeCallback()
        await module.handle_public_manager(
            callback,
            self.data,
            object(),
            object(),
            object(),
        )

        self.assertEqual(len(callback.answers), 1)
        self.assertIn("Не удалось", callback.answers[0][0][0])
        self.assertTrue(callback.answers[0][1]["show_alert"])

    async def test_success_answer_failure_is_not_reported_as_download_failure(self) -> None:
        sends: list[dict[str, object]] = []

        async def send(*args, **kwargs):
            sends.append(kwargs)

        module._send_as_document = send
        callback = FakeCallback()
        answer_error = RuntimeError("callback expired")
        callback.answer_error = answer_error

        with self.assertRaises(RuntimeError) as caught:
            await module.handle_public_manager(
                callback,
                self.data,
                object(),
                object(),
                object(),
            )

        self.assertIs(caught.exception, answer_error)
        self.assertEqual(len(sends), 1)
        self.assertEqual(len(callback.answers), 1)
        self.assertEqual(callback.answers[0][0][0], "Оригинал отправлен в личный чат.")

    async def test_download_cancellation_is_not_swallowed(self) -> None:
        async def cancel_send(*args, **kwargs):
            raise asyncio.CancelledError

        module._send_as_document = cancel_send
        callback = FakeCallback()

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_public_manager(
                callback,
                self.data,
                object(),
                object(),
                object(),
            )

        self.assertEqual(callback.answers, [])


if __name__ == "__main__":
    unittest.main()
