from __future__ import annotations

import re
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.access import AccessPolicy, is_character_editor_user
from velvet_bot.archive_catalog import get_archive_page, set_archive_media_prompt
from velvet_bot.archive_ui import (
    ArchiveMediaCallback,
    build_archive_navigation,
    format_archive_caption,
)
from velvet_bot.character_directory import validate_prompt_post_url
from velvet_bot.database import Database

router = Router(name=__name__)

_PROMPT_MARKER_RE = re.compile(r"PROMPT_MEDIA:(\d+):(\d+):(\d+)")
_URL_RE = re.compile(
    r"https://t\.me/(?:c/\d+|[A-Za-z0-9_]+)/\d+(?:\?[^\s]+)?",
    re.IGNORECASE,
)


def _prompt_marker(*, character_id: int, media_id: int, offset: int) -> str:
    return f"PROMPT_MEDIA:{character_id}:{media_id}:{offset}"


def _parse_prompt_request(message: Message) -> tuple[int, int, int] | None:
    reply = message.reply_to_message
    if reply is None:
        return None
    source = reply.text or reply.caption or ""
    match = _PROMPT_MARKER_RE.search(source)
    if match is None:
        return None
    return tuple(int(value) for value in match.groups())


def _extract_prompt_url(message: Message) -> str | None:
    text = message.text or message.caption or ""
    match = _URL_RE.search(text)
    if match is not None:
        return validate_prompt_post_url(match.group(0))

    origin = message.forward_origin
    chat = getattr(origin, "chat", None) if origin is not None else None
    message_id = getattr(origin, "message_id", None) if origin is not None else None
    username = getattr(chat, "username", None) if chat is not None else None
    if username and message_id:
        return validate_prompt_post_url(f"https://t.me/{username}/{message_id}")
    return None


def _open_media_keyboard(
    character_id: int,
    offset: int,
    media_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Вернуться к материалу",
                    callback_data=ArchiveMediaCallback(
                        action="open",
                        character_id=character_id,
                        offset=offset,
                        media_id=media_id,
                    ).pack(),
                )
            ]
        ]
    )


def _prompt_scope_text(media) -> str:
    if getattr(media, "belongs_to_set", False):
        title = getattr(media, "media_set_title", None) or "без названия"
        return (
            f"Материал входит в сет <b>{escape(str(title))}</b>. "
            "Ссылка будет закреплена сразу за всеми выбранными материалами этого сета."
        )
    return "Ссылка будет закреплена только за этой картинкой или видео."


@router.message(Command("prompt", "setprompt"))
async def handle_prompt_command_help(message: Message) -> None:
    await message.answer(
        "<b>Промт можно привязать к отдельному материалу или целому сету.</b>\n\n"
        "Откройте <code>/characters</code> → выберите персонажа → откройте архив → "
        "на нужном материале нажмите <b>📝 Привязать промт</b>.\n\n"
        "Если материал входит в медиасет, один промт автоматически появится у "
        "всех изображений этого сета. Для одиночного материала ссылка останется "
        "только у него."
    )


@router.callback_query(ArchiveMediaCallback.filter(F.action == "prompt"))
async def handle_prompt_button(
    callback: CallbackQuery,
    callback_data: ArchiveMediaCallback,
    database: Database,
) -> None:
    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше не найден.", show_alert=True)
        return
    if callback_data.media_id and page.media.id != callback_data.media_id:
        await callback.answer(
            "Архив изменился. Откройте материал заново.",
            show_alert=True,
        )
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Чат больше недоступен.", show_alert=True)
        return

    marker = _prompt_marker(
        character_id=page.character.id,
        media_id=page.media.id,
        offset=page.offset,
    )
    await callback.message.answer(
        "<b>Привязать промт</b>\n\n"
        f"Персонаж: <b>{escape(page.character.name)}</b>\n"
        f"Материал: <b>{page.offset + 1}</b> из <b>{page.total}</b>\n"
        f"{_prompt_scope_text(page.media)}\n\n"
        "Ответьте на это сообщение ссылкой на конкретный пост Telegram с промтом. "
        "Для публичного канала можно также переслать сам пост.\n\n"
        f"<code>{marker}</code>",
        reply_markup=ForceReply(
            selective=True,
            input_field_placeholder="https://t.me/channel/123",
        ),
    )
    await callback.answer("Пришлите ссылку ответом на сообщение.")


@router.message(F.reply_to_message.text.contains("PROMPT_MEDIA:"))
async def handle_prompt_link_reply(
    message: Message,
    database: Database,
    access_policy: AccessPolicy,
) -> None:
    if not (
        access_policy.allows_user(message.from_user)
        or is_character_editor_user(message.from_user)
    ):
        await message.answer(
            "Привязывать промты может только владелец или редактор архива."
        )
        return

    request = _parse_prompt_request(message)
    if request is None:
        return
    character_id, media_id, offset = request

    try:
        prompt_url = _extract_prompt_url(message)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return

    if prompt_url is None:
        await message.answer(
            "Не нашла ссылку на пост. Пришлите адрес вида "
            "<code>https://t.me/channel/123</code> ответом на предыдущее сообщение."
        )
        return

    updated = await set_archive_media_prompt(
        database,
        character_id=character_id,
        media_id=media_id,
        prompt_post_url=prompt_url,
    )
    if not updated:
        await message.answer("Материал больше не найден в архиве.")
        return

    refreshed = await get_archive_page(database, character_id, offset)
    applies_to_set = bool(
        refreshed is not None
        and refreshed.media is not None
        and refreshed.media.belongs_to_set
    )
    scope = (
        "Кнопка <b>📝 Открыть промт</b> появилась у всех материалов сета."
        if applies_to_set
        else "Кнопка <b>📝 Открыть промт</b> появилась у этого материала."
    )
    await message.answer(
        f"<b>Промт привязан.</b>\n\n{scope}",
        reply_markup=_open_media_keyboard(character_id, offset, media_id),
    )


@router.callback_query(ArchiveMediaCallback.filter(F.action == "promptremove"))
async def handle_prompt_remove(
    callback: CallbackQuery,
    callback_data: ArchiveMediaCallback,
    database: Database,
) -> None:
    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше не найден.", show_alert=True)
        return
    if callback_data.media_id and page.media.id != callback_data.media_id:
        await callback.answer(
            "Архив изменился. Откройте материал заново.",
            show_alert=True,
        )
        return

    belonged_to_set = page.media.belongs_to_set
    updated = await set_archive_media_prompt(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        prompt_post_url=None,
    )
    if not updated:
        await callback.answer("Привязка уже отсутствует.", show_alert=True)
        return

    refreshed = await get_archive_page(database, page.character.id, page.offset)
    if (
        refreshed is not None
        and refreshed.media is not None
        and isinstance(callback.message, Message)
    ):
        await callback.message.edit_caption(
            caption=format_archive_caption(refreshed),
            reply_markup=build_archive_navigation(refreshed),
        )
    await callback.answer(
        "Промт отвязан от всего сета." if belonged_to_set else "Промт отвязан.",
        show_alert=True,
    )
