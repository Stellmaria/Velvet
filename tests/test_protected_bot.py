import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.methods import SendDocument, SendMessage, SendPhoto

import velvet_bot.public_archive_display as public_display
from velvet_bot.protected_bot import ProtectedMediaBot, protect_private_media_method
from velvet_bot.public_preview_overrides import send_viewer_archive_page


class ProtectedMediaBotTests(unittest.TestCase):
    def test_public_private_photo_is_protected(self) -> None:
        method = SendPhoto(chat_id=100, photo="photo-file-id")

        changed = protect_private_media_method(
            method,
            unprotected_private_user_ids={8179531132},
        )

        self.assertTrue(changed)
        self.assertIs(method.protect_content, True)

    def test_allowed_download_recipient_remains_unprotected(self) -> None:
        method = SendDocument(chat_id=8179531132, document="document-file-id")

        changed = protect_private_media_method(
            method,
            unprotected_private_user_ids={8179531132},
        )

        self.assertFalse(changed)
        self.assertIsNot(method.protect_content, True)

    def test_internal_group_media_is_not_changed_by_private_guard(self) -> None:
        method = SendPhoto(chat_id=-1001234567890, photo="photo-file-id")

        changed = protect_private_media_method(
            method,
            unprotected_private_user_ids={8179531132},
        )

        self.assertFalse(changed)
        self.assertIsNot(method.protect_content, True)

    def test_text_menu_is_not_protected(self) -> None:
        method = SendMessage(chat_id=100, text="Archive menu")

        changed = protect_private_media_method(
            method,
            unprotected_private_user_ids={8179531132},
        )

        self.assertFalse(changed)

    def test_permanent_unprotected_recipients_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Permanent unprotected"):
            ProtectedMediaBot(
                token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
                unprotected_private_user_ids={8179531132},
            )


class ProtectedMediaBotAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_manager_download_exception_is_consumed_after_one_media_send(self) -> None:
        bot = ProtectedMediaBot(
            token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
        )
        first = SendDocument(chat_id=8179531132, document="original-file-id")
        second = SendPhoto(chat_id=8179531132, photo="archive-photo-id")

        try:
            with patch.object(Bot, "__call__", new=AsyncMock(return_value=object())):
                bot.allow_unprotected_private_user(8179531132)
                await bot(first)
                await bot(second)
        finally:
            await bot.session.close()

        self.assertIsNot(first.protect_content, True)
        self.assertIs(second.protect_content, True)

    async def test_public_archive_photo_is_protected_in_group_chat(self) -> None:
        sent_message = SimpleNamespace()
        bot = SimpleNamespace(send_photo=AsyncMock(return_value=sent_message))
        page = SimpleNamespace(
            media=SimpleNamespace(
                media_type="photo",
                telegram_file_id="archive-photo-id",
                is_spoiler=False,
                is_image_document=False,
            )
        )

        with (
            patch.object(
                public_display,
                "load_public_state",
                new=AsyncMock(return_value=SimpleNamespace()),
            ),
            patch.object(
                public_display,
                "build_viewer_keyboard",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "velvet_bot.public_preview_overrides.format_public_archive_caption",
                return_value="Archive caption",
            ),
        ):
            result = await send_viewer_archive_page(
                bot=bot,
                database=SimpleNamespace(),
                chat_id=-1001234567890,
                page=page,
                viewer_user_id=100,
            )

        self.assertIs(result, sent_message)
        self.assertIs(bot.send_photo.await_args.kwargs["protect_content"], True)


if __name__ == "__main__":
    unittest.main()
