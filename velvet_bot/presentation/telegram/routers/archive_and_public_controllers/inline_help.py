from __future__ import annotations

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

router = Router(name=__name__)


@router.inline_query()
async def handle_inline_help(query: InlineQuery, bot_username: str) -> None:
    requested = " ".join(query.query.split())
    character = requested.removeprefix("save ").strip() if requested else "Аид"
    instruction = (
        "Чтобы сохранить медиа, выйдите из inline-режима, ответьте на нужное "
        "фото или видео и отправьте обычным сообщением:\n\n"
        f"<code>@{bot_username} save {character or 'Аид'}</code>"
    )
    await query.answer(
        [
            InlineQueryResultArticle(
                id="guest-save-help",
                title="Сохранить медиа в Velvet Archive",
                description="Нужен обычный вызов Guest Mode ответом на медиа.",
                input_message_content=InputTextMessageContent(
                    message_text=instruction,
                    parse_mode=ParseMode.HTML,
                ),
            )
        ],
        cache_time=1,
        is_personal=True,
    )
