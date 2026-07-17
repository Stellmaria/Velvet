from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database
from velvet_bot.owner_callbacks import owner_callback
from velvet_bot.services.media_save import save_media_from_message
from velvet_bot.services.telegram_exports import import_export_from_message
from velvet_bot.services.telegram_publications import create_publication_draft


MEDIA_ACTIONS = frozenset(
    {
        "save_media",
        "save_spoiler",
        "check_post",
        "import_channel",
        "import_discussion",
    }
)


def _main_back_markup() -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Все действия", callback_data=owner_callback("actions"))],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data=owner_callback("menu"))],
        ]
    )


def _format_import_result(result) -> str:
    summary = result.summary
    source_label = "канал" if summary.source_kind == "channel" else "обсуждение"
    duplicate = "\n\n⚠️ Этот файл уже импортировался ранее." if summary.duplicate_import else ""
    text = (
        f"<b>Импорт завершён: {source_label}</b>\n\n"
        f"Источник: <b>{escape(summary.source_name)}</b>\n"
        f"Chat ID: <code>{summary.source_chat_id}</code>\n"
        f"Записей: <b>{summary.total_records}</b>\n"
        f"Импортировано: <b>{summary.imported_messages}</b>\n"
        f"Публикаций / альбомов: <b>{summary.publication_count}</b>\n"
        f"Промтов: <b>{summary.prompt_publications}</b>\n"
        f"Хэштегов: <b>{summary.hashtag_count}</b>\n"
        f"Персонажей сопоставлено: <b>{summary.character_matches}</b>"
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


async def handle_owner_media_action(
    *,
    message: Message,
    owner_action: str,
    value: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    analytics_channel_ids: frozenset[int],
    actor_id: int | None,
) -> bool:
    if owner_action not in MEDIA_ACTIONS:
        return False

    if owner_action in {"save_media", "save_spoiler"}:
        if not value:
            raise ValueError("Укажите имя персонажа в подписи к медиа.")
        response = await save_media_from_message(
            database,
            bot,
            audit_logger,
            request_message=message,
            source_message=message,
            character_name=value,
            actor_id=actor_id,
            spoiler=owner_action == "save_spoiler",
        )
        await message.answer(response)
        return True

    if owner_action == "check_post":
        if actor_id is None:
            raise ValueError("Не удалось определить владельца черновика.")
        draft = await create_publication_draft(
            database,
            message,
            analytics_channel_ids=analytics_channel_ids,
            owner_id=actor_id,
        )
        await message.answer(
            f"<b>Черновик №{draft.id} создан и проверен.</b>\n\n"
            f"Ошибок: <b>{draft.validation_error_count}</b>\n"
            f"Предупреждений: <b>{draft.validation_warning_count}</b>\n\n"
            "Откройте раздел «Публикации» в главном меню для редактирования, "
            "расписания или отправки.",
            reply_markup=_main_back_markup(),
        )
        return True

    status = await message.answer("⏳ Читаю экспорт и обновляю статистику.")
    result = await import_export_from_message(
        database,
        bot,
        message,
        analytics_channel_ids=analytics_channel_ids,
        source_kind=("channel" if owner_action == "import_channel" else "discussion"),
        target_chat_value=(value if owner_action == "import_discussion" else None),
        imported_by=actor_id,
    )
    await status.edit_text(_format_import_result(result))
    return True


__all__ = ("MEDIA_ACTIONS", "handle_owner_media_action")
