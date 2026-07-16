from __future__ import annotations

import re
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.database import Database
from velvet_bot.post_classification import POST_TYPE_LABELS
from velvet_bot.publication_worker import publish_publication_draft
from velvet_bot.publication_workflow import (
    PublicationDraft,
    cancel_publication,
    capture_publication_inbox,
    create_draft_from_message,
    get_publication_draft,
    list_publication_drafts,
    retry_publication,
    schedule_publication,
    set_publication_spoiler,
    update_publication_text,
    validate_publication_draft,
)

router = Router(name=__name__)

_SECTION_STATUSES = {
    "drafts": ("draft", "checked"),
    "queue": ("scheduled", "publishing"),
    "errors": ("error",),
    "published": ("published",),
    "cancelled": ("cancelled",),
}
_SECTION_LABELS = {
    "drafts": "Черновики",
    "queue": "Очередь",
    "errors": "Ошибки",
    "published": "Опубликованные",
    "cancelled": "Отменённые",
}
_SCHEDULE_MARKER = re.compile(r"PUBLICATION_SCHEDULE:(\d+)")
_TEXT_MARKER = re.compile(r"PUBLICATION_TEXT:(\d+)")


class PublicationCallback(CallbackData, prefix="pubq"):
    action: str
    draft_id: int = 0
    page: int = 0
    section: str = "drafts"


def _cb(
    action: str,
    *,
    draft_id: int = 0,
    page: int = 0,
    section: str = "drafts",
) -> str:
    return PublicationCallback(
        action=action,
        draft_id=draft_id,
        page=page,
        section=section,
    ).pack()


async def _safe_edit(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


def _center_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧪 Как проверить пост",
                    callback_data=_cb("help"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📝 Черновики",
                    callback_data=_cb("list", section="drafts"),
                ),
                InlineKeyboardButton(
                    text="📅 Очередь",
                    callback_data=_cb("list", section="queue"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Ошибки",
                    callback_data=_cb("list", section="errors"),
                ),
                InlineKeyboardButton(
                    text="✅ Опубликованные",
                    callback_data=_cb("list", section="published"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📦 Отменённые",
                    callback_data=_cb("list", section="cancelled"),
                ),
                InlineKeyboardButton(text="✖ Закрыть", callback_data=_cb("close")),
            ],
        ]
    )


def _center_text() -> str:
    return (
        "<b>Центр публикаций Velvet</b>\n\n"
        "Здесь пост проходит проверку, сохраняется как черновик, "
        "публикуется сразу или ставится в очередь.\n\n"
        "Чтобы создать черновик, отправьте или перешлите пост в этот чат, "
        "затем ответьте на него командой <code>/checkpost</code>."
    )


def _status_label(draft: PublicationDraft) -> str:
    return {
        "draft": "черновик",
        "checked": "проверен",
        "scheduled": "запланирован",
        "publishing": "публикуется",
        "published": "опубликован",
        "error": "ошибка",
        "cancelled": "отменён",
    }.get(draft.status, draft.status)


def _validation_icon(draft: PublicationDraft) -> str:
    return {
        "passed": "✅",
        "warning": "⚠️",
        "failed": "❌",
        "pending": "⏳",
    }.get(draft.validation_status, "•")


def _draft_title(draft: PublicationDraft) -> str:
    text = " ".join(draft.text_content.split())
    if text:
        return text[:42] + ("…" if len(text) > 42 else "")
    if draft.items:
        return f"Медиа: {len(draft.items)}"
    return "Пустой черновик"


def _format_local(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return "—"
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return value.astimezone(zone).strftime("%d.%m.%Y %H:%M")


def _draft_text(draft: PublicationDraft, timezone_name: str) -> str:
    issue_lines = []
    for issue in draft.validation_report:
        marker = "❌" if issue.severity == "error" else "⚠️"
        issue_lines.append(
            f"{marker} <b>{escape(issue.title)}</b>\n"
            f"   {escape(issue.detail)}"
        )
    issues = "\n".join(issue_lines) or "✅ Ошибок и предупреждений нет."
    excerpt = escape(draft.text_content[:700])
    if len(draft.text_content) > 700:
        excerpt += "…"
    return (
        f"<b>Публикация №{draft.id}</b>\n\n"
        f"Статус: <b>{escape(_status_label(draft))}</b>\n"
        f"Проверка: {_validation_icon(draft)} "
        f"ошибок {draft.validation_error_count}, "
        f"предупреждений {draft.validation_warning_count}\n"
        f"Тип: <b>{escape(POST_TYPE_LABELS.get(draft.post_type, draft.post_type))}</b>\n"
        f"Медиа: <b>{len(draft.items)}</b>\n"
        f"Блюр: <b>{'включён' if draft.has_spoiler else 'выключен'}</b>\n"
        f"Запланировано: <b>{_format_local(draft.scheduled_at, timezone_name)}</b>\n"
        f"Опубликовано: <b>{_format_local(draft.published_at, timezone_name)}</b>\n\n"
        f"<b>Проверка</b>\n{issues}\n\n"
        f"<b>Текст</b>\n{excerpt or '—'}"
        + (
            f"\n\n<b>Последняя ошибка</b>\n<code>{escape(draft.last_error)}</code>"
            if draft.last_error
            else ""
        )
    )


def _draft_keyboard(draft: PublicationDraft, *, section: str, page: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if draft.status != "published":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Перепроверить",
                    callback_data=_cb("recheck", draft_id=draft.id, section=section, page=page),
                ),
                InlineKeyboardButton(
                    text=("🌫 Убрать блюр" if draft.has_spoiler else "🌫 Включить блюр"),
                    callback_data=_cb("spoiler", draft_id=draft.id, section=section, page=page),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="✏️ Изменить текст",
                    callback_data=_cb("edittext", draft_id=draft.id, section=section, page=page),
                ),
                InlineKeyboardButton(
                    text="📅 Запланировать",
                    callback_data=_cb("schedule", draft_id=draft.id, section=section, page=page),
                ),
            ]
        )
        if draft.validation_error_count == 0 and draft.status not in {"publishing", "scheduled"}:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="📣 Опубликовать сейчас",
                        callback_data=_cb("publish", draft_id=draft.id, section=section, page=page),
                    )
                ]
            )
        if draft.status == "error":
            rows.append(
                [
                    InlineKeyboardButton(
                        text="♻️ Вернуть в черновики",
                        callback_data=_cb("retry", draft_id=draft.id, section=section, page=page),
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Отменить",
                    callback_data=_cb("cancel", draft_id=draft.id, section=section, page=page),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К списку",
                callback_data=_cb("list", section=section, page=page),
            ),
            InlineKeyboardButton(text="🏠 Центр", callback_data=_cb("menu")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_draft(
    callback: CallbackQuery,
    database: Database,
    draft_id: int,
    *,
    section: str,
    page: int,
    publication_timezone: str,
) -> None:
    draft = await get_publication_draft(
        database,
        draft_id,
        owner_id=callback.from_user.id,
    )
    if draft is None:
        await callback.answer("Черновик не найден.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _safe_edit(
        callback.message,
        _draft_text(draft, publication_timezone),
        _draft_keyboard(draft, section=section, page=page),
    )


async def _show_list(
    callback: CallbackQuery,
    database: Database,
    *,
    section: str,
    page: int,
) -> None:
    statuses = _SECTION_STATUSES.get(section, _SECTION_STATUSES["drafts"])
    result = await list_publication_drafts(
        database,
        owner_id=callback.from_user.id,
        statuses=statuses,
        page=page,
    )
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{_validation_icon(draft)} #{draft.id} · "
                    f"{_draft_title(draft)}"
                ),
                callback_data=_cb(
                    "open",
                    draft_id=draft.id,
                    section=section,
                    page=result.page,
                ),
            )
        ]
        for draft in result.items
    ]
    if result.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_cb(
                        "list",
                        section=section,
                        page=(result.page - 1) % result.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{result.page + 1} / {result.total_pages}",
                    callback_data=_cb("noop"),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_cb(
                        "list",
                        section=section,
                        page=(result.page + 1) % result.total_pages,
                    ),
                ),
            ]
        )
    rows.append([InlineKeyboardButton(text="↩️ Центр", callback_data=_cb("menu"))])
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _safe_edit(
        callback.message,
        f"<b>{escape(_SECTION_LABELS.get(section, section))}</b>\n\n"
        f"Найдено: <b>{result.total_items}</b>",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(Command("publish", "publishing", "publications"))
async def handle_publication_center(message: Message) -> None:
    await message.answer(_center_text(), reply_markup=_center_keyboard())


@router.message(Command("checkpost"))
async def handle_check_post(
    message: Message,
    database: Database,
    analytics_channel_ids: frozenset[int],
    publication_timezone: str = "Europe/Berlin",
) -> None:
    source = message.reply_to_message
    if source is None:
        await message.answer(
            "Отправьте или перешлите пост в личный чат с ботом, затем ответьте "
            "на него командой <code>/checkpost</code>."
        )
        return
    if not analytics_channel_ids:
        await message.answer("Основной канал публикаций не настроен.")
        return
    target_chat_id = sorted(analytics_channel_ids)[0]
    draft = await create_draft_from_message(
        database,
        source,
        owner_id=message.from_user.id,
        target_chat_id=target_chat_id,
    )
    await message.answer(
        _draft_text(draft, publication_timezone),
        reply_markup=_draft_keyboard(draft, section="drafts", page=0),
    )


@router.callback_query(PublicationCallback.filter())
async def handle_publication_callback(
    callback: CallbackQuery,
    callback_data: PublicationCallback,
    database: Database,
    bot: Bot,
    publication_timezone: str = "Europe/Berlin",
) -> None:
    action = callback_data.action
    if action == "noop":
        await callback.answer()
        return
    if action == "close":
        if isinstance(callback.message, Message):
            await callback.message.delete()
        await callback.answer()
        return
    if action == "menu":
        if isinstance(callback.message, Message):
            await _safe_edit(callback.message, _center_text(), _center_keyboard())
        await callback.answer()
        return
    if action == "help":
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                "<b>Как проверить публикацию</b>\n\n"
                "1. Отправьте текст, медиа или перешлите готовый пост боту.\n"
                "2. Для альбома дождитесь загрузки всех файлов.\n"
                "3. Ответьте на любой элемент командой <code>/checkpost</code>.\n"
                "4. Исправьте ошибки, включите блюр и выберите публикацию сейчас "
                "или расписание.",
                InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Центр", callback_data=_cb("menu"))]
                    ]
                ),
            )
        await callback.answer()
        return
    if action == "list":
        await _show_list(
            callback,
            database,
            section=callback_data.section,
            page=callback_data.page,
        )
        await callback.answer()
        return
    if action == "open":
        await _show_draft(
            callback,
            database,
            callback_data.draft_id,
            section=callback_data.section,
            page=callback_data.page,
            publication_timezone=publication_timezone,
        )
        await callback.answer()
        return

    draft = await get_publication_draft(
        database,
        callback_data.draft_id,
        owner_id=callback.from_user.id,
    )
    if draft is None:
        await callback.answer("Черновик не найден.", show_alert=True)
        return

    if action == "recheck":
        await validate_publication_draft(
            database,
            draft.id,
            owner_id=callback.from_user.id,
        )
        await _show_draft(
            callback,
            database,
            draft.id,
            section=callback_data.section,
            page=callback_data.page,
            publication_timezone=publication_timezone,
        )
        await callback.answer("Проверка обновлена.")
        return
    if action == "spoiler":
        await set_publication_spoiler(
            database,
            draft.id,
            owner_id=callback.from_user.id,
            enabled=not draft.has_spoiler,
        )
        await _show_draft(
            callback,
            database,
            draft.id,
            section=callback_data.section,
            page=callback_data.page,
            publication_timezone=publication_timezone,
        )
        await callback.answer("Блюр изменён.")
        return
    if action == "edittext":
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"<b>Новый текст для публикации №{draft.id}</b>\n\n"
                "Ответьте на это сообщение полным новым текстом.\n"
                f"<code>PUBLICATION_TEXT:{draft.id}</code>",
                reply_markup=ForceReply(selective=True),
            )
        await callback.answer()
        return
    if action == "schedule":
        if draft.validation_error_count:
            await callback.answer("Сначала исправьте ошибки проверки.", show_alert=True)
            return
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"<b>Дата публикации №{draft.id}</b>\n\n"
                "Ответьте датой в формате <code>18.07.2026 20:30</code>.\n"
                f"Часовой пояс: <code>{escape(publication_timezone)}</code>\n"
                f"<code>PUBLICATION_SCHEDULE:{draft.id}</code>",
                reply_markup=ForceReply(selective=True),
            )
        await callback.answer()
        return
    if action == "publish":
        if draft.validation_error_count:
            await callback.answer("Публикация заблокирована ошибками.", show_alert=True)
            return
        await callback.answer("Публикую…")
        try:
            result = await publish_publication_draft(
                bot,
                database,
                draft.id,
                owner_id=callback.from_user.id,
                actor_id=callback.from_user.id,
            )
        except Exception as error:
            await callback.message.answer(
                f"<b>Ошибка публикации №{draft.id}</b>\n\n"
                f"<code>{escape(str(error))}</code>"
            )
            return
        await _show_draft(
            callback,
            database,
            result.id,
            section="published",
            page=0,
            publication_timezone=publication_timezone,
        )
        return
    if action == "cancel":
        await cancel_publication(database, draft.id, owner_id=callback.from_user.id)
        await _show_list(callback, database, section="drafts", page=0)
        await callback.answer("Публикация отменена.")
        return
    if action == "retry":
        await retry_publication(database, draft.id, owner_id=callback.from_user.id)
        await _show_draft(
            callback,
            database,
            draft.id,
            section="drafts",
            page=0,
            publication_timezone=publication_timezone,
        )
        await callback.answer("Черновик возвращён на проверку.")


@router.message(F.reply_to_message)
async def handle_publication_reply(
    message: Message,
    database: Database,
    publication_timezone: str = "Europe/Berlin",
) -> None:
    reply_text = (
        message.reply_to_message.text
        or message.reply_to_message.caption
        or ""
    )
    schedule_match = _SCHEDULE_MARKER.search(reply_text)
    text_match = _TEXT_MARKER.search(reply_text)
    if schedule_match:
        draft_id = int(schedule_match.group(1))
        try:
            zone = ZoneInfo(publication_timezone)
        except ZoneInfoNotFoundError:
            zone = timezone.utc
        try:
            local_value = datetime.strptime(
                (message.text or "").strip(),
                "%d.%m.%Y %H:%M",
            ).replace(tzinfo=zone)
        except ValueError:
            await message.answer(
                "Не удалось прочитать дату. Формат: <code>18.07.2026 20:30</code>."
            )
            return
        if local_value.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            await message.answer("Дата публикации должна быть в будущем.")
            return
        draft = await schedule_publication(
            database,
            draft_id,
            owner_id=message.from_user.id,
            scheduled_at=local_value.astimezone(timezone.utc),
        )
        await message.answer(
            _draft_text(draft, publication_timezone),
            reply_markup=_draft_keyboard(draft, section="queue", page=0),
        )
        return
    if text_match:
        draft_id = int(text_match.group(1))
        draft = await update_publication_text(
            database,
            draft_id,
            owner_id=message.from_user.id,
            text=message.text or message.caption or "",
        )
        await message.answer(
            _draft_text(draft, publication_timezone),
            reply_markup=_draft_keyboard(draft, section="drafts", page=0),
        )


@router.message()
async def capture_private_publication_input(
    message: Message,
    database: Database,
) -> None:
    if message.chat.type != ChatType.PRIVATE or message.from_user is None:
        return
    text = message.text or message.caption or ""
    if text.lstrip().startswith("/"):
        return
    reply_text = (
        (message.reply_to_message.text or message.reply_to_message.caption or "")
        if message.reply_to_message
        else ""
    )
    if _SCHEDULE_MARKER.search(reply_text) or _TEXT_MARKER.search(reply_text):
        return
    await capture_publication_inbox(
        database,
        message,
        owner_id=message.from_user.id,
    )
