from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.application.owner_analytics import (
    load_discussion_stats,
    register_discussion,
)
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.analytics_access import (
    AnalyticsWorkspaceContext,
    resolve_analytics_ingest_workspace,
    resolve_analytics_workspace_context,
    workspace_owns_discussion_chat,
)
from velvet_bot.domains.workspaces.analytics_ingest import ingest_workspace_channel_post
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, WorkspaceRole
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.domains.workspaces.service import WorkspaceService
from velvet_bot.presentation.telegram.analytics_navigation import AnalyticsCallback
from velvet_bot.presentation.telegram.navigation import compact_button_text
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.presentation.telegram.routers.analytics_controllers.channel import (
    handle_channel_stats,
    handle_character_stats,
    handle_hashtag_stats,
    handle_prompt_stats,
)
from velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard import (
    handle_analytics_callback,
    handle_analytics_menu,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.telegram_analytics_import import (
    _discussion_stats_text,
)
from velvet_bot.telegram_export_import import list_tracked_discussions
from velvet_bot.workspace_ui import WorkspaceCallback

router = Router(name=__name__)
logger = logging.getLogger(__name__)


class PersonalAnalyticsWorkspaceFilter(BaseFilter):
    def __init__(self, minimum_role: WorkspaceRole = "reviewer") -> None:
        self.minimum_role = minimum_role

    async def __call__(
        self,
        event: Message | CallbackQuery,
        database: Database,
        workspace_service: WorkspaceService,
        analytics_channel_ids: frozenset[int],
    ) -> dict[str, AnalyticsWorkspaceContext] | bool:
        user = event.from_user
        if user is None:
            return False
        context = await resolve_analytics_workspace_context(
            database,
            workspace_service,
            user_id=int(user.id),
            minimum_role=self.minimum_role,
            system_channel_ids=analytics_channel_ids,
        )
        if context.is_system:
            return False
        return {"personal_analytics_context": context}


class PersonalAnalyticsIngestFilter(BaseFilter):
    async def __call__(
        self,
        message: Message,
        database: Database,
        analytics_channel_ids: frozenset[int],
    ) -> dict[str, int] | bool:
        workspace_id = await resolve_analytics_ingest_workspace(
            database,
            chat_id=int(message.chat.id),
            system_channel_ids=analytics_channel_ids,
        )
        if workspace_id is None or workspace_id == DEFAULT_WORKSPACE_ID:
            return False
        return {"analytics_ingest_workspace_id": workspace_id}


async def _reject_access(
    event: Message | CallbackQuery,
    context: AnalyticsWorkspaceContext,
) -> bool:
    if context.allowed:
        return False
    text = context.error or "Для пространства не настроен канал аналитики."
    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
    else:
        await event.answer(escape(text))
    return True


async def _ingest(
    message: Message,
    database: Database,
    workspace_id: int,
    audit_logger: TelegramAuditLogger | None,
) -> None:
    try:
        parsed = await ingest_workspace_channel_post(
            database,
            message,
            workspace_id=workspace_id,
        )
        logger.info(
            "Captured workspace channel post workspace=%s channel=%s message=%s",
            workspace_id,
            parsed.channel_id,
            parsed.message_id,
        )
    except Exception as error:  # p2-approved-boundary: report-workspace-analytics-ingest-failure
        logger.exception(
            "Workspace channel analytics ingest failed workspace_id=%s chat_id=%s",
            workspace_id,
            message.chat.id,
        )
        if audit_logger is not None:
            await audit_logger.error(
                "Ошибка аналитики пространства",
                error,
                workspace_id=workspace_id,
                channel_id=message.chat.id,
                message_id=message.message_id,
            )


@router.channel_post(PersonalAnalyticsIngestFilter())
async def handle_workspace_channel_post(
    message: Message,
    database: Database,
    analytics_ingest_workspace_id: int,
    audit_logger: TelegramAuditLogger | None = None,
) -> None:
    await _ingest(
        message,
        database,
        analytics_ingest_workspace_id,
        audit_logger,
    )


@router.edited_channel_post(PersonalAnalyticsIngestFilter())
async def handle_workspace_edited_channel_post(
    message: Message,
    database: Database,
    analytics_ingest_workspace_id: int,
    audit_logger: TelegramAuditLogger | None = None,
) -> None:
    await _ingest(
        message,
        database,
        analytics_ingest_workspace_id,
        audit_logger,
    )


@router.message(
    Command("analytics", "analyticsmenu"),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_analytics_menu(
    message: Message,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_analytics_context):
        return
    await handle_analytics_menu(message)


@router.callback_query(
    WorkspaceCallback.filter((F.action == "module") & (F.module_key == "analytics")),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_analytics_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    """Enter scoped analytics from the visible workspace module button."""
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    if callback_data.workspace_id != personal_analytics_context.workspace_id:
        await callback.answer(
            "Кнопка относится к другому пространству. Откройте меню заново.",
            show_alert=True,
        )
        return
    if not personal_analytics_context.allowed:
        await callback.message.answer(
            "<b>📊 Аналитика пока не подключена</b>\n\n"
            + escape(
                personal_analytics_context.error
                or "Для этого пространства не подключён канал аналитики."
            )
            + "\n\nВыберите канал аналитики в дополнительных подключениях. После "
            "этого бот будет собирать только публикации этого пространства.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔌 Открыть подключения",
                            callback_data=guided_workspace_callback(
                                "connections",
                                workspace_id=personal_analytics_context.workspace_id,
                            ),
                        )
                    ]
                ]
            ),
        )
        await callback.answer()
        return
    await handle_analytics_menu(callback.message)
    await callback.answer()


@router.message(
    Command("channelstats", "stats"),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_channel_stats(
    message: Message,
    database: Database,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_analytics_context):
        return
    await handle_channel_stats(
        message,
        database,
        frozenset(personal_analytics_context.channel_ids),
    )


@router.message(
    Command("promptstats"),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_prompt_stats(
    message: Message,
    database: Database,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_analytics_context):
        return
    await handle_prompt_stats(
        message,
        database,
        frozenset(personal_analytics_context.channel_ids),
    )


@router.message(
    Command("hashtagstats", "tagstats"),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_hashtag_stats(
    message: Message,
    command: CommandObject,
    database: Database,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_analytics_context):
        return
    await handle_hashtag_stats(
        message,
        command,
        database,
        frozenset(personal_analytics_context.channel_ids),
    )


@router.message(
    Command("characterstats"),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_character_stats(
    message: Message,
    database: Database,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_analytics_context):
        return
    await handle_character_stats(
        message,
        database,
        frozenset(personal_analytics_context.channel_ids),
    )


@router.message(
    Command("trackdiscussion"),
    PersonalAnalyticsWorkspaceFilter("editor"),
)
async def handle_workspace_track_discussion(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_analytics_context):
        return
    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP} and not command.args:
        chat_id = int(message.chat.id)
        title = message.chat.title
        username = message.chat.username
    else:
        if not command.args:
            await message.answer(
                "Запустите команду внутри чата обсуждений или укажите ID в личке."
            )
            return
        try:
            chat_id = int(command.args.strip())
        except ValueError:
            await message.answer("Chat ID должен быть числом.")
            return
        chat = await bot.get_chat(chat_id)
        title = chat.title
        username = chat.username

    try:
        await WorkspaceRepository(database).upsert_channel(
            workspace_id=personal_analytics_context.workspace_id,
            kind="discussion",
            chat_id=chat_id,
            url=(f"https://t.me/{username}" if username else None),
        )
        result = await register_discussion(
            database,
            frozenset(personal_analytics_context.channel_ids),
            chat_id=chat_id,
            title=title,
            username=username,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        "<b>Чат обсуждений подключён к пространству.</b>\n\n"
        f"Название: <b>{escape(result.title or 'без названия')}</b>\n"
        f"Chat ID: <code>{result.chat_id}</code>\n"
        f"Связан с каналом: <code>{result.parent_channel_id}</code>"
    )


@router.message(
    Command("discussionstats"),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_discussion_stats(
    message: Message,
    command: CommandObject,
    database: Database,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_analytics_context):
        return
    raw_value = (command.args or "").strip()
    if not raw_value:
        if not personal_analytics_context.discussion_chat_ids:
            await message.answer(
                "Чат обсуждений ещё не подключён к активному пространству."
            )
            return
        raw_value = str(personal_analytics_context.discussion_chat_ids[0])
    try:
        chat_id = int(raw_value)
    except ValueError:
        await message.answer("Chat ID должен быть числом.")
        return
    if not await workspace_owns_discussion_chat(
        database,
        workspace_id=personal_analytics_context.workspace_id,
        chat_id=chat_id,
    ):
        await message.answer("Этот чат не принадлежит активному пространству.")
        return
    try:
        result = await load_discussion_stats(
            database,
            frozenset(personal_analytics_context.channel_ids),
            raw_value,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(_discussion_stats_text(result))


@router.callback_query(
    AnalyticsCallback.filter(),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_analytics_callback(
    callback: CallbackQuery,
    callback_data: AnalyticsCallback,
    database: Database,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    await _handle_workspace_analytics_callback(
        callback,
        callback_data,
        database,
        personal_analytics_context,
    )


async def _show_workspace_discussions(
    callback: CallbackQuery,
    database: Database,
    context: AnalyticsWorkspaceContext,
    callback_data: AnalyticsCallback,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    sources = await list_tracked_discussions(
        database,
        parent_channel_id=context.primary_channel_id,
    )
    allowed_ids = set(context.discussion_chat_ids)
    filtered = [source for source in sources if int(source[0]) in allowed_ids]
    rows = [
        [
            InlineKeyboardButton(
                text=compact_button_text(f"💬 {title or chat_id}"),
                callback_data=AnalyticsCallback(
                    action="discussion",
                    period=callback_data.period,
                    source_id=int(chat_id),
                ).pack(),
            )
        ]
        for chat_id, title, _ in filtered
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Аналитика",
                callback_data=AnalyticsCallback(
                    action="menu",
                    period=callback_data.period,
                ).pack(),
            )
        ]
    )
    text = "<b>Обсуждения пространства</b>\n\n"
    text += (
        "Выберите подключённый чат."
        if filtered
        else "К активному пространству пока не подключён чат обсуждений."
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


async def _handle_workspace_analytics_callback(
    callback: CallbackQuery,
    callback_data: AnalyticsCallback,
    database: Database,
    context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(callback, context):
        return
    if callback_data.action == "discussions":
        await _show_workspace_discussions(
            callback,
            database,
            context,
            callback_data,
        )
        return
    if callback_data.action in {"discussion", "participants"}:
        if callback_data.source_id not in context.discussion_chat_ids:
            owns_source = await workspace_owns_discussion_chat(
                database,
                workspace_id=context.workspace_id,
                chat_id=callback_data.source_id,
            )
            if not owns_source:
                await callback.answer(
                    "Этот чат обсуждения не принадлежит активному пространству.",
                    show_alert=True,
                )
                return
    await handle_analytics_callback(
        callback,
        callback_data,
        database,
        frozenset(context.channel_ids),
    )


__all__ = ("router",)
