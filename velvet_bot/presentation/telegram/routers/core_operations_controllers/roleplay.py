from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.enums import ChatAction, ChatType
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

from velvet_bot.domains.roleplay.client import RoleplayClientError
from velvet_bot.domains.roleplay.service import (
    RoleplayInactiveError,
    RoleplayService,
    RoleplayUnavailableError,
)

router = Router(name=__name__)
_TELEGRAM_CHUNK_LIMIT = 3900


class ActiveRoleplayFilter(BaseFilter):
    async def __call__(self, message: Message, **data: object) -> bool:
        if (
            message.chat.type != ChatType.PRIVATE
            or message.from_user is None
            or not message.text
        ):
            return False
        if message.text.lstrip().startswith("/"):
            return False
        service = data.get("roleplay_service")
        return isinstance(service, RoleplayService) and await service.is_active(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
        )


def _actor_ids(message: Message) -> tuple[int, int] | None:
    if message.from_user is None:
        return None
    return int(message.chat.id), int(message.from_user.id)


def _command_argument(message: Message) -> str:
    text = (message.text or "").strip()
    _, separator, tail = text.partition(" ")
    if separator:
        return tail.strip()
    replied = message.reply_to_message
    return (replied.text or replied.caption or "").strip() if replied else ""


def _split_text(
    text: str,
    *,
    limit: int = _TELEGRAM_CHUNK_LIMIT,
) -> tuple[str, ...]:
    remaining = text.strip()
    if not remaining:
        return ("Модель вернула пустой ответ.",)
    chunks: list[str] = []
    while len(remaining) > limit:
        boundary = remaining.rfind("\n\n", 0, limit)
        if boundary < limit // 2:
            boundary = remaining.rfind("\n", 0, limit)
        if boundary < limit // 2:
            boundary = remaining.rfind(" ", 0, limit)
        if boundary < limit // 2:
            boundary = limit
        chunks.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    if remaining:
        chunks.append(remaining)
    return tuple(chunks)


async def _answer_plain(message: Message, text: str) -> None:
    await message.answer(text, parse_mode=None)


def _public_roleplay_error(error: BaseException) -> str:
    if isinstance(error, RoleplayUnavailableError):
        return "Ролевая модель временно недоступна. Попробуйте позже."
    if isinstance(error, RoleplayInactiveError):
        return "РЛ-режим сейчас выключен. Включите его командой /rp_on."
    if isinstance(error, ValueError):
        return "Не удалось обработать запрос. Проверьте текст и повторите."
    return "Не удалось получить ответ ролевой модели. Попробуйте позже."


async def _generate_reply(
    message: Message,
    *,
    roleplay_service: RoleplayService,
    text: str,
    activate: bool,
) -> None:
    actor = _actor_ids(message)
    if actor is None:
        await _answer_plain(message, "Не удалось определить пользователя.")
        return
    try:
        await message.bot.send_chat_action(actor[0], ChatAction.TYPING)
        reply = await roleplay_service.reply(
            chat_id=actor[0],
            user_id=actor[1],
            text=text,
            activate=activate,
        )
    except (
        RoleplayClientError,
        RoleplayInactiveError,
        RoleplayUnavailableError,
        ValueError,
    ) as error:
        await _answer_plain(message, _public_roleplay_error(error))
        return
    for chunk in _split_text(reply.text):
        await _answer_plain(message, chunk)


@router.message(Command("rp_help"))
async def handle_roleplay_help(message: Message) -> None:
    await message.answer(
        "<b>Ролевая игра</b>\n\n"
        "<code>/rp_on</code> — включить свободный РЛ-режим в этом ЛС.\n"
        "<code>/rp текст</code> — включить режим и сразу отправить реплику.\n"
        "<code>/rp_prompt канон</code> — сохранить постоянный канон и стиль. "
        "Можно ответить командой на длинное сообщение.\n"
        "<code>/rp_status</code> — показать режим и объём памяти.\n"
        "<code>/rp_reset</code> — очистить историю и резюме, сохранив канон.\n"
        "<code>/rp_off</code> — выключить перехват обычных сообщений."
    )


@router.message(Command("rp_on"))
async def handle_roleplay_on(
    message: Message,
    roleplay_service: RoleplayService,
) -> None:
    actor = _actor_ids(message)
    if actor is None:
        return
    try:
        await roleplay_service.start(chat_id=actor[0], user_id=actor[1])
    except RoleplayUnavailableError as error:
        await _answer_plain(message, _public_roleplay_error(error))
        return
    await message.answer(
        "<b>РЛ-режим включён.</b> Обычные текстовые сообщения в этом ЛС "
        "теперь идут текстовой модели. Для канона используйте "
        "<code>/rp_prompt</code>."
    )


@router.message(Command("rp_off"))
async def handle_roleplay_off(
    message: Message,
    roleplay_service: RoleplayService,
) -> None:
    actor = _actor_ids(message)
    if actor is None:
        return
    await roleplay_service.stop(chat_id=actor[0], user_id=actor[1])
    await message.answer("<b>РЛ-режим выключен.</b> История и канон сохранены.")


@router.message(Command("rp_reset"))
async def handle_roleplay_reset(
    message: Message,
    roleplay_service: RoleplayService,
) -> None:
    actor = _actor_ids(message)
    if actor is None:
        return
    await roleplay_service.reset(chat_id=actor[0], user_id=actor[1])
    await message.answer(
        "История РЛ и краткая память очищены. Постоянный канон сохранён."
    )


@router.message(Command("rp_prompt"))
async def handle_roleplay_prompt(
    message: Message,
    roleplay_service: RoleplayService,
) -> None:
    actor = _actor_ids(message)
    if actor is None:
        return
    canon = _command_argument(message)
    if not canon:
        session = await roleplay_service.get_session(
            chat_id=actor[0],
            user_id=actor[1],
        )
        if session is None or not session.system_prompt.strip():
            await message.answer(
                "Канон пока не задан. Используйте <code>/rp_prompt текст канона</code> "
                "или ответьте этой командой на сообщение с каноном."
            )
            return
        preview = escape(session.system_prompt[:3000])
        suffix = "…" if len(session.system_prompt) > 3000 else ""
        await message.answer(f"<b>Текущий канон</b>\n\n{preview}{suffix}")
        return
    try:
        await roleplay_service.set_canon(
            chat_id=actor[0],
            user_id=actor[1],
            canon=canon,
        )
    except ValueError as error:
        await _answer_plain(message, _public_roleplay_error(error))
        return
    await message.answer(
        f"Канон сохранён: <b>{len(canon)}</b> символов. Он будет добавляться "
        "к каждой РЛ-реплике вместе с памятью сцены."
    )


@router.message(Command("rp_status"))
async def handle_roleplay_status(
    message: Message,
    roleplay_service: RoleplayService,
) -> None:
    actor = _actor_ids(message)
    if actor is None:
        return
    session = await roleplay_service.get_session(
        chat_id=actor[0],
        user_id=actor[1],
    )
    enabled = bool(session and session.enabled)
    canon_length = len(session.system_prompt) if session else 0
    summary_length = len(session.summary) if session else 0
    await message.answer(
        "<b>РЛ-статус</b>\n\n"
        f"Режим: <b>{'включён' if enabled else 'выключен'}</b>\n"
        f"Канон: <b>{canon_length}</b> символов\n"
        f"Долговременное резюме: <b>{summary_length}</b> символов\n"
        f"Живая история: до <b>{roleplay_service.max_history_messages}</b> сообщений"
    )


@router.message(Command("rp"))
async def handle_roleplay_command(
    message: Message,
    roleplay_service: RoleplayService,
) -> None:
    text = _command_argument(message)
    if not text:
        await message.answer(
            "Добавьте реплику после команды: <code>/rp текст</code>."
        )
        return
    await _generate_reply(
        message,
        roleplay_service=roleplay_service,
        text=text,
        activate=True,
    )


@router.message(ActiveRoleplayFilter())
async def handle_active_roleplay_message(
    message: Message,
    roleplay_service: RoleplayService,
) -> None:
    await _generate_reply(
        message,
        roleplay_service=roleplay_service,
        text=message.text or "",
        activate=False,
    )


__all__ = ("router",)
