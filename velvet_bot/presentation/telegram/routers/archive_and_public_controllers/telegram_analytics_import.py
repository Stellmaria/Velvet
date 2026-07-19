from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.application.owner_analytics import (
    DiscussionStats,
    ImportResult,
    load_discussion_stats,
    register_discussion,
)
from velvet_bot.database import Database
from velvet_bot.services.telegram_exports import import_export_from_message

router = Router(name=__name__)


def _format_date(value) -> str:
    return value.astimezone().strftime("%d.%m.%Y") if value else "—"


def _import_summary_text(result: ImportResult) -> str:
    summary = result.summary
    duplicate = "\n\n⚠️ Этот файл уже импортировался ранее." if summary.duplicate_import else ""
    source_label = "канал" if summary.source_kind == "channel" else "обсуждение"
    text = (
        f"<b>Импорт завершён: {source_label}</b>\n\n"
        f"Источник: <b>{escape(summary.source_name)}</b>\n"
        f"Chat ID: <code>{summary.source_chat_id}</code>\n"
        f"Записей в экспорте: <b>{summary.total_records}</b>\n"
        f"Сообщений импортировано: <b>{summary.imported_messages}</b>\n"
        f"Публикаций / альбомов: <b>{summary.publication_count}</b>\n"
        f"Распознано промтов: <b>{summary.prompt_publications}</b>\n"
        f"Использований хэштегов: <b>{summary.hashtag_count}</b>\n"
        f"Персонажей сопоставлено: <b>{summary.character_matches}</b>\n"
        f"Реакций в экспорте: <b>{summary.reaction_count}</b>"
        f"{duplicate}"
    )
    if result.relink is not None:
        text += (
            "\n\n<b>Связка с публикациями</b>\n"
            f"Корней найдено: <b>{result.relink.roots_marked}</b>\n"
            f"Комментариев привязано: <b>{result.relink.comments_linked}</b>\n"
            f"Веток сопоставлено: <b>{result.relink.threads_linked}</b>"
        )
    return text


def _discussion_stats_text(result: DiscussionStats) -> str:
    overview = result.overview
    participant_lines = "\n".join(
        f"• <b>{escape(item.sender_name)}</b> — {item.message_count} сообщений, "
        f"ответов {item.reply_count}, медиа {item.media_count}"
        for item in result.participants
    ) or "• данных пока нет"
    hashtag_lines = "\n".join(
        f"• <code>#{escape(item.hashtag)}</code> — {item.publication_count}"
        for item in result.hashtags
    ) or "• хэштегов пока нет"
    return (
        "<b>Статистика чата обсуждений</b>\n\n"
        f"Chat ID: <code>{result.chat_id}</code>\n"
        f"Период: <b>{_format_date(overview.first_message_at)}</b> — "
        f"<b>{_format_date(overview.last_message_at)}</b>\n"
        f"Сообщений: <b>{overview.total_messages}</b>\n"
        f"Публикаций / альбомов: <b>{overview.total_publications}</b>\n"
        f"Участников: <b>{overview.unique_participants}</b>\n"
        f"Ответов: <b>{overview.reply_messages}</b>\n"
        f"Медиа: <b>{overview.media_messages}</b>\n"
        f"Под спойлером: <b>{overview.spoiler_messages}</b>\n"
        f"Хэштегов: <b>{overview.total_hashtag_uses}</b> "
        f"({overview.unique_hashtags} уникальных)\n"
        f"Реакций из экспорта: <b>{overview.total_reactions}</b>\n\n"
        f"<b>Активные участники</b>\n{participant_lines}\n\n"
        f"<b>Частые хэштеги</b>\n{hashtag_lines}"
    )


async def _handle_import(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    analytics_channel_ids: frozenset[int],
    *,
    source_kind: str,
) -> None:
    status = await message.answer(
        "⏳ Читаю экспорт и обновляю статистику. Медиафайлы не импортируются."
    )
    try:
        result = await import_export_from_message(
            database,
            bot,
            message,
            analytics_channel_ids=analytics_channel_ids,
            source_kind=source_kind,
            target_chat_value=(command.args if source_kind == "discussion" else None),
            imported_by=message.from_user.id if message.from_user else None,
        )
    except (ValueError, RuntimeError) as error:
        await status.edit_text(f"<b>Импорт не выполнен</b>\n\n{escape(str(error))}")
        return
    await status.edit_text(_import_summary_text(result))


@router.message(Command("importchannel"))
async def handle_import_channel(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    analytics_channel_ids: frozenset[int],
) -> None:
    await _handle_import(
        message,
        command,
        database,
        bot,
        analytics_channel_ids,
        source_kind="channel",
    )


@router.message(Command("importdiscussion"))
async def handle_import_discussion(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    analytics_channel_ids: frozenset[int],
) -> None:
    await _handle_import(
        message,
        command,
        database,
        bot,
        analytics_channel_ids,
        source_kind="discussion",
    )


@router.message(Command("trackdiscussion"))
async def handle_track_discussion(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    analytics_channel_ids: frozenset[int],
) -> None:
    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP} and not command.args:
        chat_id = message.chat.id
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
        result = await register_discussion(
            database,
            analytics_channel_ids,
            chat_id=chat_id,
            title=title,
            username=username,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        "<b>Чат обсуждений подключён.</b>\n\n"
        f"Название: <b>{escape(result.title or 'без названия')}</b>\n"
        f"Chat ID: <code>{result.chat_id}</code>\n"
        f"Связан с каналом: <code>{result.parent_channel_id}</code>"
    )


@router.message(Command("discussionstats"))
async def handle_discussion_stats(
    message: Message,
    command: CommandObject,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    try:
        result = await load_discussion_stats(
            database,
            analytics_channel_ids,
            command.args,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(_discussion_stats_text(result))
