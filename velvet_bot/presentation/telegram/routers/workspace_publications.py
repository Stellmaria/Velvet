from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.app.publication import build_publication_service
from velvet_bot.application.publication_actions import build_publication_actions
from velvet_bot.database import Database
from velvet_bot.domains.publication import PublicationDraft
from velvet_bot.domains.workspaces.publication_access import (
    PublicationWorkspaceContext,
    resolve_publication_workspace_context,
)
from velvet_bot.domains.workspaces.service import WorkspaceService
from velvet_bot.presentation.telegram.navigation import compact_button_text
from velvet_bot.presentation.telegram.routers.publication.center import (
    PublicationCallback,
    _SECTION_LABELS,
    _SECTION_STATUSES,
    _SCHEDULE_MARKER,
    _TEXT_MARKER,
    _center_keyboard,
    _center_text,
    _draft_keyboard,
    _draft_text,
    _draft_title,
    _report_publication_failure,
    _safe_edit,
    _validation_icon,
)
from velvet_bot.publication_drafts import capture_publication_inbox
from velvet_bot.services.telegram_publications import create_publication_draft
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.workspace_ui import WorkspaceCallback

entry_router = Router(name=f"{__name__}.entry")
router = Router(name=__name__)


class PersonalPublicationWorkspaceFilter(BaseFilter):
    async def __call__(
        self,
        event: Message | CallbackQuery,
        database: Database,
        workspace_service: WorkspaceService,
        analytics_channel_ids: frozenset[int],
        publication_timezone: str = "Europe/Berlin",
    ) -> dict[str, PublicationWorkspaceContext] | bool:
        user = event.from_user
        if user is None:
            return False
        context = await resolve_publication_workspace_context(
            database,
            workspace_service,
            user_id=int(user.id),
            minimum_role="editor",
            analytics_channel_ids=analytics_channel_ids,
            system_timezone=publication_timezone,
        )
        if context.is_system:
            return False
        return {"personal_publication_context": context}


async def _reject_access(
    event: Message | CallbackQuery,
    context: PublicationWorkspaceContext,
) -> bool:
    if context.error is None and context.target_chat_id is not None:
        return False
    message = context.error or "Для пространства не настроен канал публикаций."
    if isinstance(event, CallbackQuery):
        await event.answer(message, show_alert=True)
    else:
        await event.answer(escape(message))
    return True


async def _show_draft(
    callback: CallbackQuery,
    database: Database,
    context: PublicationWorkspaceContext,
    draft_id: int,
    *,
    section: str,
    page: int,
) -> None:
    draft = await build_publication_actions(database).get_draft(
        draft_id,
        owner_id=callback.from_user.id,
        workspace_id=context.workspace_id,
    )
    if draft is None:
        await callback.answer("Черновик не найден в активном пространстве.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _safe_edit(
        callback.message,
        _draft_text(draft, context.timezone),
        _draft_keyboard(draft, section=section, page=page),
    )


async def _show_list(
    callback: CallbackQuery,
    database: Database,
    context: PublicationWorkspaceContext,
    *,
    section: str,
    page: int,
) -> None:
    statuses = _SECTION_STATUSES.get(section, _SECTION_STATUSES["drafts"])
    result = await build_publication_actions(database).list_drafts(
        owner_id=callback.from_user.id,
        statuses=statuses,
        page=page,
        workspace_id=context.workspace_id,
    )
    rows = [
        [
            InlineKeyboardButton(
                text=compact_button_text(
                    f"{_validation_icon(draft)} #{draft.id} · {_draft_title(draft)}"
                ),
                callback_data=PublicationCallback(
                    action="open",
                    draft_id=draft.id,
                    page=result.page,
                    section=section,
                ).pack(),
            )
        ]
        for draft in result.items
    ]
    if result.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=PublicationCallback(
                        action="list",
                        page=(result.page - 1) % result.total_pages,
                        section=section,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=f"{result.page + 1} / {result.total_pages}",
                    callback_data=PublicationCallback(action="noop").pack(),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=PublicationCallback(
                        action="list",
                        page=(result.page + 1) % result.total_pages,
                        section=section,
                    ).pack(),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Центр",
                callback_data=PublicationCallback(action="menu").pack(),
            )
        ]
    )
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _safe_edit(
        callback.message,
        f"<b>{escape(_SECTION_LABELS.get(section, section))}</b>\n\n"
        f"Найдено в этом пространстве: <b>{result.total_items}</b>",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(
    Command("publish", "publishing", "publications"),
    PersonalPublicationWorkspaceFilter(),
)
async def handle_workspace_publication_center(
    message: Message,
    personal_publication_context: PublicationWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_publication_context):
        return
    await message.answer(
        _center_text(),
        reply_markup=_center_keyboard(),
    )


@entry_router.callback_query(
    WorkspaceCallback.filter(
        (F.action == "module") & (F.module_key == "publications")
    ),
    PersonalPublicationWorkspaceFilter(),
)
async def handle_workspace_publication_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    personal_publication_context: PublicationWorkspaceContext,
) -> None:
    """Open the real tenant-aware publication center from workspace home."""
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    if callback_data.workspace_id != personal_publication_context.workspace_id:
        await callback.answer(
            "Кнопка относится к другому пространству. Откройте меню заново.",
            show_alert=True,
        )
        return
    if (
        personal_publication_context.error is not None
        or personal_publication_context.target_chat_id is None
    ):
        await _safe_edit(
            callback.message,
            "<b>📣 Публикации пока не подключены</b>\n\n"
            + escape(
                personal_publication_context.error
                or "Для этого пространства не выбран канал публикаций."
            )
            + "\n\nПодключите канал в разделе «Дополнительные подключения». "
            "После этого здесь появятся черновики, проверка и очередь.",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔌 Открыть подключения",
                            callback_data=guided_workspace_callback(
                                "connections",
                                workspace_id=personal_publication_context.workspace_id,
                            ),
                        )
                    ]
                ]
            ),
        )
        await callback.answer()
        return
    await _safe_edit(callback.message, _center_text(), _center_keyboard())
    await callback.answer()


@router.message(
    Command("checkpost"),
    PersonalPublicationWorkspaceFilter(),
)
async def handle_workspace_check_post(
    message: Message,
    database: Database,
    analytics_channel_ids: frozenset[int],
    personal_publication_context: PublicationWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_publication_context):
        return
    source = message.reply_to_message
    if source is None:
        await message.answer(
            "Отправьте или перешлите пост в личный чат с ботом, затем ответьте "
            "на него командой <code>/checkpost</code>."
        )
        return
    draft = await create_publication_draft(
        database,
        source,
        analytics_channel_ids=analytics_channel_ids,
        owner_id=message.from_user.id,
        workspace_id=personal_publication_context.workspace_id,
        target_chat_id=personal_publication_context.target_chat_id,
    )
    await message.answer(
        _draft_text(draft, personal_publication_context.timezone),
        reply_markup=_draft_keyboard(draft, section="drafts", page=0),
    )


@router.callback_query(
    PublicationCallback.filter(),
    PersonalPublicationWorkspaceFilter(),
)
async def handle_workspace_publication_callback(
    callback: CallbackQuery,
    callback_data: PublicationCallback,
    personal_publication_context: PublicationWorkspaceContext,
    database: Database,
    bot: Bot,
) -> None:
    await _handle_workspace_publication_callback(
        callback,
        callback_data,
        personal_publication_context,
        database,
        bot,
    )


async def _handle_workspace_publication_callback(
    callback: CallbackQuery,
    callback_data: PublicationCallback,
    context: PublicationWorkspaceContext,
    database: Database,
    bot: Bot,
) -> None:
    if await _reject_access(callback, context):
        return
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
                "<b>Как проверить публикацию пространства</b>\n\n"
                "1. Отправьте текст, медиа или готовый пост боту.\n"
                "2. Для альбома дождитесь загрузки всех файлов.\n"
                "3. Ответьте командой <code>/checkpost</code>.\n"
                "4. После проверки опубликуйте сразу или добавьте в очередь.\n\n"
                "Черновики, очередь и хэштеги изолированы от других пространств.",
                InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="↩️ Центр",
                                callback_data=PublicationCallback(action="menu").pack(),
                            )
                        ]
                    ]
                ),
            )
        await callback.answer()
        return
    if action == "list":
        await _show_list(
            callback,
            database,
            context,
            section=callback_data.section,
            page=callback_data.page,
        )
        await callback.answer()
        return
    if action == "open":
        await _show_draft(
            callback,
            database,
            context,
            callback_data.draft_id,
            section=callback_data.section,
            page=callback_data.page,
        )
        await callback.answer()
        return

    actions = build_publication_actions(database)
    draft = await actions.get_draft(
        callback_data.draft_id,
        owner_id=callback.from_user.id,
        workspace_id=context.workspace_id,
    )
    if draft is None:
        await callback.answer("Черновик не найден в активном пространстве.", show_alert=True)
        return

    if action == "recheck":
        await actions.recheck(
            draft.id,
            owner_id=callback.from_user.id,
            workspace_id=context.workspace_id,
        )
        await _show_draft(
            callback,
            database,
            context,
            draft.id,
            section=callback_data.section,
            page=callback_data.page,
        )
        await callback.answer("Проверка обновлена.")
        return
    if action == "spoiler":
        await actions.set_spoiler(
            draft.id,
            owner_id=callback.from_user.id,
            enabled=not draft.has_spoiler,
            workspace_id=context.workspace_id,
        )
        await _show_draft(
            callback,
            database,
            context,
            draft.id,
            section=callback_data.section,
            page=callback_data.page,
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
                f"Часовой пояс пространства: <code>{escape(context.timezone)}</code>\n"
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
            result = await build_publication_service(bot, database).publish(
                draft.id,
                owner_id=callback.from_user.id,
                actor_id=callback.from_user.id,
                workspace_id=context.workspace_id,
            )
        except Exception as error:  # p2-approved-boundary: report-workspace-publication-failure
            await _report_publication_failure(
                callback=callback,
                bot=bot,
                draft_id=draft.id,
                error=error,
            )
            return
        await _show_draft(
            callback,
            database,
            context,
            result.id,
            section="published",
            page=0,
        )
        return
    if action == "cancel":
        await actions.cancel(
            draft.id,
            owner_id=callback.from_user.id,
            workspace_id=context.workspace_id,
        )
        await _show_list(callback, database, context, section="drafts", page=0)
        await callback.answer("Публикация отменена.")
        return
    if action == "retry":
        await actions.retry(
            draft.id,
            owner_id=callback.from_user.id,
            workspace_id=context.workspace_id,
        )
        await _show_draft(
            callback,
            database,
            context,
            draft.id,
            section="drafts",
            page=0,
        )
        await callback.answer("Черновик возвращён на проверку.")


@router.message(
    F.reply_to_message,
    PersonalPublicationWorkspaceFilter(),
)
async def handle_workspace_publication_reply(
    message: Message,
    database: Database,
    personal_publication_context: PublicationWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_publication_context):
        return
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
            zone = ZoneInfo(personal_publication_context.timezone)
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
        draft = await build_publication_actions(database).schedule(
            draft_id,
            owner_id=message.from_user.id,
            scheduled_at=local_value.astimezone(timezone.utc),
            workspace_id=personal_publication_context.workspace_id,
        )
        await message.answer(
            _draft_text(draft, personal_publication_context.timezone),
            reply_markup=_draft_keyboard(draft, section="queue", page=0),
        )
        return
    if text_match:
        draft_id = int(text_match.group(1))
        draft = await build_publication_actions(database).update_text(
            draft_id,
            owner_id=message.from_user.id,
            text=message.text or message.caption or "",
            workspace_id=personal_publication_context.workspace_id,
        )
        await message.answer(
            _draft_text(draft, personal_publication_context.timezone),
            reply_markup=_draft_keyboard(draft, section="drafts", page=0),
        )


@router.message(
    F.chat.type == ChatType.PRIVATE,
    PersonalPublicationWorkspaceFilter(),
)
async def capture_workspace_publication_input(
    message: Message,
    database: Database,
    personal_publication_context: PublicationWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_publication_context):
        return
    if message.from_user is None:
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
        workspace_id=personal_publication_context.workspace_id,
    )


__all__ = ("entry_router", "router")
