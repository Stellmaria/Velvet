from __future__ import annotations

import io
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.channel_analytics import list_hashtag_stats
from velvet_bot.database import Database
from velvet_bot.discussion_analytics import (
    get_discussion_overview,
    list_participant_stats,
)
from velvet_bot.discussion_insights import rebuild_discussion_threads
from velvet_bot.telegram_export_import import (
    ExportImportSummary,
    import_telegram_export,
    list_tracked_discussions,
    register_tracked_source,
)

router = Router(name=__name__)

BOT_DOWNLOAD_LIMIT = 20 * 1024 * 1024


def _primary_channel_id(analytics_channel_ids: frozenset[int]) -> int | None:
    return sorted(analytics_channel_ids)[0] if analytics_channel_ids else None


def _format_date(value) -> str:
    return value.astimezone().strftime("%d.%m.%Y") if value else "—"


def _import_summary_text(summary: ExportImportSummary) -> str:
    duplicate = "\n\n⚠️ Этот файл уже импортировался ранее." if summary.duplicate_import else ""
    source_label = "канал" if summary.source_kind == "channel" else "обсуждение"
    return (
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


async def _download_export_document(message: Message, bot: Bot) -> tuple[bytes, str]:
    source = message.reply_to_message
    document = source.document if source is not None else None
    if document is None:
        raise ValueError(
            "Отправьте <code>result.json</code> в личный чат с ботом и ответьте "
            "на файл командой импорта."
        )

    file_name = document.file_name or "result.json"
    lowered = file_name.casefold()
    if not lowered.endswith((".json", ".zip")):
        raise ValueError("Поддерживаются только result.json и ZIP экспорта Telegram.")
    if document.file_size and document.file_size > BOT_DOWNLOAD_LIMIT:
        raise ValueError(
            "Файл больше 20 МБ, стандартный Telegram Bot API не сможет его скачать. "
            "Извлеките из ZIP только <code>result.json</code> и отправьте его, либо "
            "используйте локальный скрипт <code>scripts/import_telegram_export.py</code>."
        )

    destination = io.BytesIO()
    await bot.download(document.file_id, destination=destination, seek=True)
    payload = destination.getvalue()
    if not payload:
        raise ValueError("Telegram вернул пустой файл.")
    return payload, file_name


async def _handle_import(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    analytics_channel_ids: frozenset[int],
    *,
    source_kind: str,
) -> None:
    try:
        raw, file_name = await _download_export_document(message, bot)
    except ValueError as error:
        await message.answer(str(error))
        return

    primary_channel_id = _primary_channel_id(analytics_channel_ids)
    target_chat_id: int | None = None
    if source_kind == "channel":
        target_chat_id = primary_channel_id
    elif command.args:
        try:
            target_chat_id = int(command.args.strip())
        except ValueError:
            await message.answer(
                "ID обсуждения должен быть числом: "
                "<code>/importdiscussion -1001234567890</code>"
            )
            return

    status = await message.answer(
        "⏳ Читаю экспорт и обновляю статистику. Медиафайлы не импортируются."
    )
    try:
        summary = await import_telegram_export(
            database,
            raw=raw,
            file_name=file_name,
            source_kind=source_kind,
            target_chat_id=target_chat_id,
            parent_channel_id=(primary_channel_id if source_kind == "discussion" else None),
            imported_by=message.from_user.id if message.from_user else None,
        )
        relink_text = ""
        if source_kind == "discussion":
            relink = await rebuild_discussion_threads(
                database,
                summary.source_chat_id,
            )
            relink_text = (
                "\n\n<b>Связка с публикациями</b>\n"
                f"Корней найдено: <b>{relink.roots_marked}</b>\n"
                f"Комментариев привязано: <b>{relink.comments_linked}</b>\n"
                f"Веток сопоставлено: <b>{relink.threads_linked}</b>"
            )
    except (ValueError, RuntimeError) as error:
        await status.edit_text(f"<b>Импорт не выполнен</b>\n\n{escape(str(error))}")
        return
    await status.edit_text(_import_summary_text(summary) + relink_text)


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
    primary_channel_id = _primary_channel_id(analytics_channel_ids)
    if primary_channel_id is None:
        await message.answer("Основной канал аналитики не настроен.")
        return

    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP} and not command.args:
        chat_id = message.chat.id
        title = message.chat.title
        username = message.chat.username
    else:
        if not command.args:
            await message.answer(
                "Запустите <code>/trackdiscussion</code> внутри чата обсуждений "
                "или укажите ID в личке: "
                "<code>/trackdiscussion -1001234567890</code>."
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

    await register_tracked_source(
        database,
        chat_id=chat_id,
        title=title,
        username=username,
        source_kind="discussion",
        parent_channel_id=primary_channel_id,
    )
    await message.answer(
        "<b>Чат обсуждений подключён.</b>\n\n"
        f"Название: <b>{escape(title or 'без названия')}</b>\n"
        f"Chat ID: <code>{chat_id}</code>\n"
        f"Связан с каналом: <code>{primary_channel_id}</code>\n\n"
        "Новые сообщения будут анализироваться автоматически. Для старой истории "
        "отправьте result.json и ответьте <code>/importdiscussion</code>."
    )


@router.message(Command("discussionstats"))
async def handle_discussion_stats(
    message: Message,
    command: CommandObject,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    primary_channel_id = _primary_channel_id(analytics_channel_ids)
    if command.args:
        try:
            chat_id = int(command.args.strip())
        except ValueError:
            await message.answer("Chat ID должен быть числом.")
            return
    else:
        discussions = await list_tracked_discussions(
            database,
            parent_channel_id=primary_channel_id,
        )
        if not discussions:
            await message.answer(
                "Чат обсуждений ещё не подключён. Запустите "
                "<code>/trackdiscussion</code> внутри него."
            )
            return
        chat_id = discussions[0][0]

    overview = await get_discussion_overview(database, chat_id)
    participants = await list_participant_stats(database, chat_id, limit=15)
    hashtags = await list_hashtag_stats(database, chat_id, limit=15)

    participant_lines = "\n".join(
        f"• <b>{escape(item.sender_name)}</b> — {item.message_count} сообщений, "
        f"ответов {item.reply_count}, медиа {item.media_count}"
        for item in participants
    ) or "• данных пока нет"
    hashtag_lines = "\n".join(
        f"• <code>#{escape(item.hashtag)}</code> — {item.publication_count}"
        for item in hashtags
    ) or "• хэштегов пока нет"

    await message.answer(
        "<b>Статистика чата обсуждений</b>\n\n"
        f"Chat ID: <code>{chat_id}</code>\n"
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
