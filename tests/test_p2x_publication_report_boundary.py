from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.publication_center as module


class FakeTelegramAPIError(Exception):
    pass


class FakeMessage:
    def __init__(self) -> None:
        self.reports: list[str] = []
        self.report_error: BaseException | None = None

    async def answer(self, text: str, **kwargs) -> None:
        self.reports.append(text)
        if self.report_error is not None:
            raise self.report_error


class FakeCallback:
    def __init__(self, *, message: object | None = None) -> None:
        self.from_user = SimpleNamespace(id=17)
        self.message = FakeMessage() if message is None else message
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))


class FakeBot:
    def __init__(self) -> None:
        self.private_reports: list[dict[str, object]] = []
        self.report_error: BaseException | None = None

    async def send_message(self, **kwargs) -> None:
        self.private_reports.append(kwargs)
        if self.report_error is not None:
            raise self.report_error


class FakeActions:
    def __init__(self) -> None:
        self.draft = SimpleNamespace(id=12, validation_error_count=0)

    async def get_draft(self, draft_id: int, *, owner_id: int):
        return self.draft


class FakePublicationService:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    async def publish(self, draft_id: int, *, owner_id: int, actor_id: int):
        raise self.error


class PublicationReportBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_message = module.Message
        self.original_telegram_api_error = module.TelegramAPIError
        self.original_build_actions = module.build_publication_actions
        self.original_build_service = module.build_publication_service
        self.original_show_draft = module._show_draft

        module.Message = FakeMessage
        module.TelegramAPIError = FakeTelegramAPIError
        self.actions = FakeActions()
        module.build_publication_actions = lambda database: self.actions

        async def unexpected_show(*args, **kwargs):
            raise AssertionError("draft view must not render after publication failure")

        module._show_draft = unexpected_show

    def tearDown(self) -> None:
        module.Message = self.original_message
        module.TelegramAPIError = self.original_telegram_api_error
        module.build_publication_actions = self.original_build_actions
        module.build_publication_service = self.original_build_service
        module._show_draft = self.original_show_draft

    @staticmethod
    def _data() -> SimpleNamespace:
        return SimpleNamespace(
            action="publish",
            draft_id=12,
            section="drafts",
            page=0,
        )

    async def test_publish_failure_is_reported_in_source_chat(self) -> None:
        error = RuntimeError("<provider unavailable>")
        service = FakePublicationService(error)
        module.build_publication_service = lambda bot, database: service
        callback = FakeCallback()
        bot = FakeBot()

        await module.handle_publication_callback(
            callback,
            self._data(),
            object(),
            bot,
        )

        self.assertEqual(callback.answers[0][0][0], "Публикую…")
        self.assertEqual(len(callback.message.reports), 1)
        self.assertIn("Ошибка публикации №12", callback.message.reports[0])
        self.assertIn("&lt;provider unavailable&gt;", callback.message.reports[0])
        self.assertEqual(bot.private_reports, [])

    async def test_source_report_failure_falls_back_to_private_message(self) -> None:
        callback = FakeCallback()
        callback.message.report_error = FakeTelegramAPIError("source unavailable")
        bot = FakeBot()

        await module._report_publication_failure(
            callback=callback,
            bot=bot,
            draft_id=12,
            error=RuntimeError("publish failed"),
        )

        self.assertEqual(len(callback.message.reports), 1)
        self.assertEqual(len(bot.private_reports), 1)
        self.assertEqual(bot.private_reports[0]["chat_id"], 17)
        self.assertIn("publish failed", bot.private_reports[0]["text"])

    async def test_missing_source_message_uses_private_fallback(self) -> None:
        callback = FakeCallback(message=object())
        bot = FakeBot()

        await module._report_publication_failure(
            callback=callback,
            bot=bot,
            draft_id=12,
            error=RuntimeError("publish failed"),
        )

        self.assertEqual(len(bot.private_reports), 1)
        self.assertEqual(bot.private_reports[0]["chat_id"], 17)

    async def test_reporting_api_failures_do_not_replace_publish_failure(self) -> None:
        callback = FakeCallback()
        callback.message.report_error = FakeTelegramAPIError("source unavailable")
        bot = FakeBot()
        bot.report_error = FakeTelegramAPIError("private unavailable")

        await module._report_publication_failure(
            callback=callback,
            bot=bot,
            draft_id=12,
            error=RuntimeError("publish failed"),
        )

        self.assertEqual(len(callback.message.reports), 1)
        self.assertEqual(len(bot.private_reports), 1)

    async def test_publish_cancellation_is_not_swallowed(self) -> None:
        service = FakePublicationService(asyncio.CancelledError())
        module.build_publication_service = lambda bot, database: service
        callback = FakeCallback()
        bot = FakeBot()

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_publication_callback(
                callback,
                self._data(),
                object(),
                bot,
            )

        self.assertEqual(len(callback.answers), 1)
        self.assertEqual(callback.answers[0][0][0], "Публикую…")
        self.assertEqual(callback.message.reports, [])
        self.assertEqual(bot.private_reports, [])


if __name__ == "__main__":
    unittest.main()
