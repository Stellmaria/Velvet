from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText
from aiogram.types import Chat, Message, PhotoSize

import velvet_bot.presentation.telegram.auf_editing as auf_editing
from velvet_bot.presentation.telegram.shared.editing import (
    edit_or_answer_callback_text,
)


def _message(*, with_photo: bool = False) -> Message:
    photo = (
        [PhotoSize(file_id="photo", file_unique_id="unique", width=1, height=1)]
        if with_photo
        else None
    )
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=1, type=ChatType.PRIVATE),
        photo=photo,
    )


def _bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(
        method=EditMessageText(chat_id=1, message_id=1, text="card"),
        message=message,
    )


class CallbackEditOrAnswerContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_message_is_edited_and_callback_is_acknowledged(self) -> None:
        callback = SimpleNamespace(message=_message(), answer=AsyncMock())
        edit = AsyncMock()
        answer = AsyncMock()

        with (
            patch.object(Message, "edit_text", new=edit),
            patch.object(Message, "answer", new=answer),
        ):
            await edit_or_answer_callback_text(
                callback,  # type: ignore[arg-type]
                text="card",
                reply_markup=object(),  # type: ignore[arg-type]
            )

        edit.assert_awaited_once()
        answer.assert_not_awaited()
        callback.answer.assert_awaited_once_with()

    async def test_unchanged_message_is_not_duplicated(self) -> None:
        callback = SimpleNamespace(message=_message(), answer=AsyncMock())
        edit = AsyncMock(side_effect=_bad_request("message is not modified"))
        answer = AsyncMock()

        with (
            patch.object(Message, "edit_text", new=edit),
            patch.object(Message, "answer", new=answer),
        ):
            await edit_or_answer_callback_text(
                callback,  # type: ignore[arg-type]
                text="card",
                reply_markup=object(),  # type: ignore[arg-type]
            )

        answer.assert_not_awaited()
        callback.answer.assert_awaited_once_with()

    async def test_other_edit_rejection_falls_back_to_new_answer(self) -> None:
        callback = SimpleNamespace(message=_message(), answer=AsyncMock())
        edit = AsyncMock(side_effect=_bad_request("message cannot be edited"))
        answer = AsyncMock()

        with (
            patch.object(Message, "edit_text", new=edit),
            patch.object(Message, "answer", new=answer),
        ):
            await edit_or_answer_callback_text(
                callback,  # type: ignore[arg-type]
                text="card",
                reply_markup=object(),  # type: ignore[arg-type]
            )

        answer.assert_awaited_once()
        callback.answer.assert_awaited_once_with()

    async def test_media_message_uses_new_answer_without_edit_attempt(self) -> None:
        callback = SimpleNamespace(message=_message(with_photo=True), answer=AsyncMock())
        edit = AsyncMock()
        answer = AsyncMock()

        with (
            patch.object(Message, "edit_text", new=edit),
            patch.object(Message, "answer", new=answer),
        ):
            await edit_or_answer_callback_text(
                callback,  # type: ignore[arg-type]
                text="card",
                reply_markup=object(),  # type: ignore[arg-type]
            )

        edit.assert_not_awaited()
        answer.assert_awaited_once()
        callback.answer.assert_awaited_once_with()


class AufEditingHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_transformer_is_applied_before_shared_rendering(self) -> None:
        render = AsyncMock()
        previous = auf_editing.install_auf_text_transformer(
            lambda value: value.replace("internal", "public")
        )
        try:
            with patch.object(auf_editing, "edit_or_answer_callback_text", new=render):
                await auf_editing.edit_or_answer_auf_callback(
                    object(),  # type: ignore[arg-type]
                    text="internal card",
                    reply_markup=object(),  # type: ignore[arg-type]
                )
        finally:
            auf_editing.install_auf_text_transformer(previous)

        render.assert_awaited_once_with(
            unittest.mock.ANY,
            text="public card",
            reply_markup=unittest.mock.ANY,
        )


if __name__ == "__main__":
    unittest.main()
