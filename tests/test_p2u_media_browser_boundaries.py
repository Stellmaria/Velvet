from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.presentation.telegram.routers.archive_and_public_controllers.media_browser as module


class FakeBot:
    def __init__(self) -> None:
        self.document_calls: list[dict[str, object]] = []

    async def send_photo(self, **kwargs):
        raise AssertionError("preview photo must not be sent after download failure")

    async def send_document(self, **kwargs):
        self.document_calls.append(kwargs)
        return "document-message"


class FakeAudit:
    def __init__(self) -> None:
        self.errors: list[tuple[str, BaseException, dict[str, object]]] = []

    async def error(self, title: str, error: BaseException, **fields) -> None:
        self.errors.append((title, error, fields))

    async def send(self, *args, **kwargs) -> None:
        raise AssertionError("success audit is not expected in failure tests")


class FakeCallback:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=17)
        self.message = object()
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))


class MediaBrowserBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_download = module._download_image_for_preview
        self.original_input_media = module.build_input_media
        self.original_caption = module.format_archive_caption
        self.original_navigation = module.build_archive_navigation
        self.original_get_page = module.get_archive_page
        self.original_delete_current = module._delete_current_item

        module.format_archive_caption = lambda page: "caption"
        module.build_archive_navigation = lambda page: "keyboard"

        self.media = SimpleNamespace(
            is_image_document=True,
            media_type="document",
            telegram_file_id="original-document",
            display_file_name="image.png",
        )
        self.page = SimpleNamespace(
            media=self.media,
            character=SimpleNamespace(name="Ada"),
            offset=2,
        )

    def tearDown(self) -> None:
        module._download_image_for_preview = self.original_download
        module.build_input_media = self.original_input_media
        module.format_archive_caption = self.original_caption
        module.build_archive_navigation = self.original_navigation
        module.get_archive_page = self.original_get_page
        module._delete_current_item = self.original_delete_current

    async def test_build_preview_failure_falls_back_to_original_media(self) -> None:
        fallback = object()

        async def fail_download(bot, media):
            raise RuntimeError("preview unavailable")

        module._download_image_for_preview = fail_download
        module.build_input_media = lambda media, caption: fallback

        result = await module._build_display_input_media(object(), self.media, "caption")
        self.assertIs(result, fallback)

    async def test_build_preview_cancellation_is_not_swallowed(self) -> None:
        async def cancel_download(bot, media):
            raise asyncio.CancelledError

        module._download_image_for_preview = cancel_download
        with self.assertRaises(asyncio.CancelledError):
            await module._build_display_input_media(object(), self.media, "caption")

    async def test_send_preview_failure_falls_back_to_document(self) -> None:
        async def fail_download(bot, media):
            raise RuntimeError("preview unavailable")

        module._download_image_for_preview = fail_download
        bot = FakeBot()
        result = await module._send_archive_page(bot, 23, self.page)

        self.assertEqual(result, "document-message")
        self.assertEqual(len(bot.document_calls), 1)
        call = bot.document_calls[0]
        self.assertEqual(call["document"], "original-document")
        self.assertEqual(call["chat_id"], 23)
        self.assertEqual(call["caption"], "caption")
        self.assertEqual(call["reply_markup"], "keyboard")

    async def test_send_preview_cancellation_is_not_swallowed(self) -> None:
        async def cancel_download(bot, media):
            raise asyncio.CancelledError

        module._download_image_for_preview = cancel_download
        bot = FakeBot()
        with self.assertRaises(asyncio.CancelledError):
            await module._send_archive_page(bot, 23, self.page)
        self.assertEqual(bot.document_calls, [])

    async def test_load_failure_is_audited_and_answered(self) -> None:
        error = RuntimeError("database unavailable")

        async def fail_load(database, character_id, offset):
            raise error

        module.get_archive_page = fail_load
        callback = FakeCallback()
        audit = FakeAudit()
        data = SimpleNamespace(action="show", character_id=7, offset=3, media_id=0)

        await module.handle_archive_media_callback(callback, data, object(), object(), audit)

        self.assertEqual(len(audit.errors), 1)
        title, recorded_error, fields = audit.errors[0]
        self.assertEqual(title, "Ошибка загрузки архива")
        self.assertIs(recorded_error, error)
        self.assertEqual(fields["character_id"], 7)
        self.assertEqual(fields["offset"], 3)
        self.assertEqual(fields["user_id"], 17)
        self.assertEqual(len(callback.answers), 1)
        self.assertTrue(callback.answers[0][1]["show_alert"])

    async def test_load_cancellation_is_not_swallowed(self) -> None:
        async def cancel_load(database, character_id, offset):
            raise asyncio.CancelledError

        module.get_archive_page = cancel_load
        callback = FakeCallback()
        audit = FakeAudit()
        data = SimpleNamespace(action="show", character_id=7, offset=3, media_id=0)

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_archive_media_callback(callback, data, object(), object(), audit)

        self.assertEqual(audit.errors, [])
        self.assertEqual(callback.answers, [])

    async def test_delete_failure_is_audited_and_answered(self) -> None:
        error = RuntimeError("delete failed")

        async def load_page(database, character_id, offset):
            return self.page

        async def fail_delete(*args, **kwargs):
            raise error

        module.get_archive_page = load_page
        module._delete_current_item = fail_delete
        callback = FakeCallback()
        audit = FakeAudit()
        data = SimpleNamespace(action="delok", character_id=7, offset=2, media_id=5)

        await module.handle_archive_media_callback(callback, data, object(), object(), audit)

        self.assertEqual(len(audit.errors), 1)
        title, recorded_error, fields = audit.errors[0]
        self.assertEqual(title, "Ошибка удаления медиа")
        self.assertIs(recorded_error, error)
        self.assertEqual(fields["character"], "Ada")
        self.assertEqual(fields["file"], "image.png")
        self.assertEqual(fields["user_id"], 17)
        self.assertEqual(len(callback.answers), 1)
        self.assertTrue(callback.answers[0][1]["show_alert"])

    async def test_delete_cancellation_is_not_swallowed(self) -> None:
        async def load_page(database, character_id, offset):
            return self.page

        async def cancel_delete(*args, **kwargs):
            raise asyncio.CancelledError

        module.get_archive_page = load_page
        module._delete_current_item = cancel_delete
        callback = FakeCallback()
        audit = FakeAudit()
        data = SimpleNamespace(action="delok", character_id=7, offset=2, media_id=5)

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_archive_media_callback(callback, data, object(), object(), audit)

        self.assertEqual(audit.errors, [])
        self.assertEqual(callback.answers, [])


if __name__ == "__main__":
    unittest.main()
