from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage

from velvet_bot.presentation.telegram import message_deletion
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers import (
    media_browser,
)


def _bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(
        method=DeleteMessage(chat_id=-1003951213065, message_id=9309),
        message=message,
    )


class MessageDeletionTests(unittest.IsolatedAsyncioTestCase):

    def test_archive_delete_flows_use_shared_idempotent_helper(self) -> None:
        for relative in (
            "velvet_bot/presentation/telegram/routers/archive_and_public_controllers/media_browser.py",
            "velvet_bot/presentation/telegram/routers/public_archive/manager.py",
        ):
            with self.subTest(path=relative):
                source = Path(relative).read_text(encoding="utf-8")
                self.assertIn("delete_message_idempotently", source)
                self.assertNotIn("_ArchiveDeleteNoiseFilter", source)

    async def test_delete_returns_deleted_when_telegram_accepts_request(self) -> None:
        bot = SimpleNamespace(delete_message=AsyncMock(return_value=True))

        result = await message_deletion.delete_message_idempotently(
            bot,
            chat_id=-1001,
            message_id=42,
        )

        self.assertEqual("deleted", result)
        bot.delete_message.assert_awaited_once_with(chat_id=-1001, message_id=42)

    async def test_missing_message_is_treated_as_already_absent(self) -> None:
        bot = SimpleNamespace(
            delete_message=AsyncMock(
                side_effect=_bad_request(
                    "Bad Request: message to delete not found"
                )
            )
        )

        result = await message_deletion.delete_message_idempotently(
            bot,
            chat_id=-1003951213065,
            message_id=9309,
        )

        self.assertEqual("already_absent", result)

    async def test_other_bad_request_is_not_suppressed(self) -> None:
        error = _bad_request("Bad Request: chat not found")
        bot = SimpleNamespace(delete_message=AsyncMock(side_effect=error))

        with self.assertRaises(TelegramBadRequest) as raised:
            await message_deletion.delete_message_idempotently(
                bot,
                chat_id=-1003951213065,
                message_id=9309,
            )

        self.assertIs(error, raised.exception)

    async def test_owner_delete_does_not_audit_already_absent_message_as_error(self) -> None:
        deleted = SimpleNamespace(
            character=SimpleNamespace(
                name="Одри Евро",
                archive_chat_id=-1003951213065,
            ),
            media=SimpleNamespace(
                id=17,
                archive_message_id=9309,
                display_file_name="019e9f75-d3c0-7993-84d3-eb42902af828.png",
            ),
            remaining_total=0,
            orphan_media_removed=False,
        )
        delete_archive_item = AsyncMock(return_value=deleted)
        original_delete_archive_item = media_browser.delete_archive_item
        media_browser.delete_archive_item = delete_archive_item
        try:
            callback = SimpleNamespace(
                from_user=SimpleNamespace(id=7221553045),
                message=object(),
                answer=AsyncMock(),
            )
            callback_data = SimpleNamespace(character_id=7, media_id=17)
            page = SimpleNamespace(media=SimpleNamespace(id=17))
            bot = SimpleNamespace(
                delete_message=AsyncMock(
                    side_effect=_bad_request(
                        "Bad Request: message to delete not found"
                    )
                )
            )
            audit = SimpleNamespace(error=AsyncMock(), send=AsyncMock())

            await media_browser._delete_current_item(
                callback,
                callback_data,
                object(),
                bot,
                audit,
                page,
            )
        finally:
            media_browser.delete_archive_item = original_delete_archive_item

        audit.error.assert_not_awaited()
        audit.send.assert_awaited_once()
        fields = audit.send.await_args.kwargs
        self.assertFalse(fields["topic_message_deleted"])
        self.assertTrue(fields["topic_message_already_absent"])
        self.assertFalse(fields["topic_message_delete_failed"])
        callback.answer.assert_awaited_once_with("Удалено.", show_alert=True)


if __name__ == "__main__":
    unittest.main()
