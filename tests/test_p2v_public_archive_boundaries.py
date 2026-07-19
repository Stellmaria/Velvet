from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.public_archive as module


class FakeTelegramAPIError(Exception):
    pass


class FakeMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=23)
        self.caption_edits: list[dict[str, object]] = []
        self.markup_edits: list[dict[str, object]] = []
        self.caption_error: BaseException | None = None
        self.markup_error: BaseException | None = None

    async def edit_caption(self, **kwargs) -> None:
        self.caption_edits.append(kwargs)
        if self.caption_error is not None:
            raise self.caption_error

    async def edit_reply_markup(self, **kwargs) -> None:
        self.markup_edits.append(kwargs)
        if self.markup_error is not None:
            raise self.markup_error


class FakeCallback:
    def __init__(self, *, user_id: int = 17, message: object | None = None) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.message = message if message is not None else FakeMessage()
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.answer_error: BaseException | None = None

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))
        if self.answer_error is not None:
            raise self.answer_error


class FakeBot:
    def __init__(self) -> None:
        self.document_calls: list[dict[str, object]] = []

    async def send_photo(self, **kwargs):
        raise AssertionError("preview photo must not be sent after download failure")

    async def send_document(self, **kwargs):
        self.document_calls.append(kwargs)
        return "document-message"


class PublicArchiveBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_message = module.Message
        self.original_telegram_api_error = module.TelegramAPIError
        self.original_download = module._download_image_for_preview
        self.original_input_media = module.build_input_media
        self.original_load_state = module._load_state
        self.original_caption = module.format_public_archive_caption
        self.original_keyboard = module.build_public_archive_keyboard
        self.original_get_page = module.get_archive_page
        self.original_toggle_like = module.toggle_public_like
        self.original_toggle_subscription = module.toggle_character_subscription

        module.Message = FakeMessage
        module.TelegramAPIError = FakeTelegramAPIError
        module.format_public_archive_caption = lambda page, state: "caption"
        module.build_public_archive_keyboard = lambda page, state, **kwargs: "keyboard"

        self.media = SimpleNamespace(
            id=11,
            is_image_document=True,
            media_type="document",
            telegram_file_id="original-document",
            display_file_name="image.png",
        )
        self.page = SimpleNamespace(
            media=self.media,
            character=SimpleNamespace(id=7, name="Ada"),
            offset=0,
            total=1,
        )
        self.state = module.PublicMediaState(
            like_count=4,
            liked_by_user=False,
            subscribed=True,
        )

        async def load_state(database, page, user_id):
            return self.state

        async def load_page(database, character_id, offset):
            return self.page

        module._load_state = load_state
        module.get_archive_page = load_page

    def tearDown(self) -> None:
        module.Message = self.original_message
        module.TelegramAPIError = self.original_telegram_api_error
        module._download_image_for_preview = self.original_download
        module.build_input_media = self.original_input_media
        module._load_state = self.original_load_state
        module.format_public_archive_caption = self.original_caption
        module.build_public_archive_keyboard = self.original_keyboard
        module.get_archive_page = self.original_get_page
        module.toggle_public_like = self.original_toggle_like
        module.toggle_character_subscription = self.original_toggle_subscription

    @staticmethod
    def _data(action: str) -> SimpleNamespace:
        return SimpleNamespace(
            action=action,
            character_id=7,
            media_id=11,
            offset=0,
            page=0,
            category="male",
            universe="bg3",
            story_id=0,
        )

    async def test_build_preview_failure_falls_back_to_original_media(self) -> None:
        fallback = object()

        async def fail_download(bot, media):
            raise RuntimeError("preview unavailable")

        module._download_image_for_preview = fail_download
        module.build_input_media = lambda media, caption: fallback
        result = await module._build_public_input_media(object(), self.page, self.state)
        self.assertIs(result, fallback)

    async def test_build_preview_cancellation_is_not_swallowed(self) -> None:
        async def cancel_download(bot, media):
            raise asyncio.CancelledError

        module._download_image_for_preview = cancel_download
        with self.assertRaises(asyncio.CancelledError):
            await module._build_public_input_media(object(), self.page, self.state)

    async def test_send_preview_failure_falls_back_to_document(self) -> None:
        async def fail_download(bot, media):
            raise RuntimeError("preview unavailable")

        module._download_image_for_preview = fail_download
        bot = FakeBot()
        result = await module._send_public_archive_page(
            bot=bot,
            database=object(),
            chat_id=23,
            page=self.page,
            viewer_user_id=17,
            menu_page=0,
        )
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
            await module._send_public_archive_page(
                bot=bot,
                database=object(),
                chat_id=23,
                page=self.page,
                viewer_user_id=17,
                menu_page=0,
            )
        self.assertEqual(bot.document_calls, [])

    async def test_like_failure_is_answered_without_ui_edit(self) -> None:
        async def fail_toggle(*args, **kwargs):
            raise RuntimeError("like write failed")

        module.toggle_public_like = fail_toggle
        callback = FakeCallback()
        await module.handle_public_archive_callback(
            callback,
            self._data("like"),
            object(),
            object(),
        )
        self.assertEqual(len(callback.answers), 1)
        self.assertIn("Не удалось", callback.answers[0][0][0])
        self.assertTrue(callback.answers[0][1]["show_alert"])
        self.assertEqual(callback.message.caption_edits, [])

    async def test_like_ui_failure_does_not_turn_success_into_failure(self) -> None:
        async def toggle(*args, **kwargs):
            return True, 5

        captured_states = []
        module.toggle_public_like = toggle
        module.build_public_archive_keyboard = (
            lambda page, state, **kwargs: captured_states.append(state) or "keyboard"
        )
        message = FakeMessage()
        message.caption_error = FakeTelegramAPIError("message unavailable")
        callback = FakeCallback(message=message)
        await module.handle_public_archive_callback(
            callback,
            self._data("like"),
            object(),
            object(),
        )
        self.assertEqual(callback.answers[0][0][0], "Отметка поставлена.")
        self.assertEqual(len(message.caption_edits), 1)
        self.assertEqual(captured_states[0].like_count, 5)
        self.assertTrue(captured_states[0].liked_by_user)
        self.assertTrue(captured_states[0].subscribed)

    async def test_like_cancellation_is_not_swallowed(self) -> None:
        async def cancel_toggle(*args, **kwargs):
            raise asyncio.CancelledError

        module.toggle_public_like = cancel_toggle
        callback = FakeCallback()
        with self.assertRaises(asyncio.CancelledError):
            await module.handle_public_archive_callback(
                callback,
                self._data("like"),
                object(),
                object(),
            )
        self.assertEqual(callback.answers, [])

    async def test_subscription_failure_is_answered_without_ui_edit(self) -> None:
        async def fail_toggle(*args, **kwargs):
            raise RuntimeError("subscription write failed")

        module.toggle_character_subscription = fail_toggle
        callback = FakeCallback()
        await module.handle_public_archive_callback(
            callback,
            self._data("sub"),
            object(),
            object(),
        )
        self.assertEqual(len(callback.answers), 1)
        self.assertIn("Не удалось", callback.answers[0][0][0])
        self.assertTrue(callback.answers[0][1]["show_alert"])
        self.assertEqual(callback.message.markup_edits, [])

    async def test_subscription_ui_failure_does_not_turn_success_into_failure(self) -> None:
        async def toggle(*args, **kwargs):
            return False

        captured_states = []
        module.toggle_character_subscription = toggle
        module.build_public_archive_keyboard = (
            lambda page, state, **kwargs: captured_states.append(state) or "keyboard"
        )
        message = FakeMessage()
        message.markup_error = FakeTelegramAPIError("message unavailable")
        callback = FakeCallback(message=message)
        await module.handle_public_archive_callback(
            callback,
            self._data("sub"),
            object(),
            object(),
        )
        self.assertEqual(callback.answers[0][0][0], "Подписка отключена.")
        self.assertTrue(callback.answers[0][1]["show_alert"])
        self.assertEqual(len(message.markup_edits), 1)
        self.assertEqual(captured_states[0].like_count, 4)
        self.assertFalse(captured_states[0].liked_by_user)
        self.assertFalse(captured_states[0].subscribed)

    async def test_subscription_cancellation_is_not_swallowed(self) -> None:
        async def cancel_toggle(*args, **kwargs):
            raise asyncio.CancelledError

        module.toggle_character_subscription = cancel_toggle
        callback = FakeCallback()
        with self.assertRaises(asyncio.CancelledError):
            await module.handle_public_archive_callback(
                callback,
                self._data("sub"),
                object(),
                object(),
            )
        self.assertEqual(callback.answers, [])


if __name__ == "__main__":
    unittest.main()
