from __future__ import annotations

import logging
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.channel_analytics import (
    ChannelOverview,
    CharacterUsageStat,
    HashtagStat,
    PromptStructureStats,
    get_channel_overview,
    get_hashtag_stat,
    get_prompt_structure_stats,
    ingest_channel_post,
    list_character_usage_stats,
    list_hashtag_stats,
    list_link_domain_stats,
    list_media_type_stats,
)
from velvet_bot.character_directory import category_label, universe_label
from velvet_bot.database import Database

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_MEDIA_LABELS = {
    "text": "текст",
    "photo": "фото",
    "video": "видео",
    "animation": "анимации",
    "document": "файлы",
    "audio": "аудио",
    "voice": "голосовые",
    "video_note": "кружки",
    "sticker": "стикеры",
    "poll": "опросы",
}


def _primary_channel_id(analytics_channel_ids: frozenset[int]) -> int | None:
    return sorted(analytics_channel_ids)[0] if analytics_channel_ids else None


def _format_date(value) -> str:
    return value.astimezone().strftime("%d.%m.%Y") if value else "—"


def _percent(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{part * 100 / total:.1f}%"


def _hashtag_lines(items: list[HashtagStat], *, limit: int = 10) -> str:
    if not items:
        return "• пока нет данных"
    lines = []
    for item in items[:limit]:
        character = f" · {escape(item.character_name)}" if item.character_name else ""
        lines.append(
            f"• <code>#{escape(item.hashtag)}</code> — "
            f"<b>{item.publication_count}</b> публикаций, "
            f"промтов {item.prompt_count}{character}"
        )
    return "\n".join(lines)


def _character_lines(items: list[CharacterUsageStat], *, limit: int = 10) -> str:
    if not items:
        return "• пока нет совпадений с карточками персонажей"
    lines = []
    for item in items[:limit]:
        details = [category_label(item.category), universe_label(item.universe)]
        if item.story_short_label:
            details.append(item.story_short_label)
        lines.append(
            f"• <b>{escape(item.name)}</b> — {item.publication_count} публикаций, "
            f"промтов {item.prompt_count} · {escape(' / '.join(details))}"
        )
    return "\n".join(lines)


def _overview_text(
    overview: ChannelOverview,
    hashtags: list[HashtagStat],
    characters: list[CharacterUsageStat],
    media_stats,
    link_stats,
) -> str:
    media_line = ", ".join(
        f"{escape(_MEDIA_LABELS.get(item.name, item.name))}: {item.count}"
        for item in media_stats
    ) or "нет данных"
    link_line = ", ".join(
        f"{escape(item.name)}: {item.count}" for item in link_stats
    ) or "нет ссылок"
    return (
        "<b>Статистика основного канала</b>\n\n"
        f"Канал: <code>{overview.channel_id}</code>\n"
        f"Период наблюдения: <b>{_format_date(overview.first_post_at)}</b> — "
        f"<b>{_format_date(overview.last_post_at)}</b>\n\n"
        f"Публикаций: <b>{overview.total_publications}</b>\n"
        f"Сообщений с учётом альбомов: <b>{overview.total_messages}</b>\n"
        f"Распознано промтов: <b>{overview.prompt_publications}</b> "
        f"({_percent(overview.prompt_publications, overview.total_publications)})\n"
        f"Медиафайлов: <b>{overview.media_messages}</b>\n"
        f"Под спойлером 18+: <b>{overview.spoiler_messages}</b>\n"
        f"Отредактировано сообщений: <b>{overview.edited_messages}</b>\n"
        f"Средняя длина текста: <b>{overview.average_text_length:.0f}</b> символов\n\n"
        f"Хэштегов использовано: <b>{overview.total_hashtag_uses}</b>\n"
        f"Уникальных хэштегов: <b>{overview.unique_hashtags}</b>\n"
        f"Персонажей сопоставлено с архивом: <b>{overview.unique_characters}</b>\n"
        f"Ссылок: <b>{overview.total_links}</b>, из них Telegram: "
        f"<b>{overview.telegram_links}</b>\n"
        f"Зафиксировано просмотров: <b>{overview.captured_views}</b>\n"
        f"Зафиксировано пересылок: <b>{overview.captured_forwards}</b>\n\n"
        f"<b>Типы контента</b>\n{media_line}\n\n"
        f"<b>Частые домены</b>\n{link_line}\n\n"
        f"<b>Топ хэштегов</b>\n{_hashtag_lines(hashtags)}\n\n"
        f"<b>Самые задействованные персонажи</b>\n"
        f"{_character_lines(characters)}"
    )


def _prompt_text(
    stats: PromptStructureStats,
    hashtags: list[HashtagStat],
) -> str:
    total = stats.prompt_publications
    return (
        "<b>Аналитика промтов канала</b>\n\n"
        f"Распознано промтов: <b>{total}</b>\n"
        f"Средняя длина: <b>{stats.average_prompt_length:.0f}</b> символов\n\n"
        f"Блок ВАЖНО: <b>{stats.with_important}</b> "
        f"({_percent(stats.with_important, total)})\n"
        f"Блок СТРОГО: <b>{stats.with_strict}</b> "
        f"({_percent(stats.with_strict, total)})\n"
        f"Negative / запреты: <b>{stats.with_negative}</b> "
        f"({_percent(stats.with_negative, total)})\n"
        f"Технический блок: <b>{stats.with_technical}</b> "
        f"({_percent(stats.with_technical, total)})\n"
        f"Палитра HEX: <b>{stats.with_palette}</b> "
        f"({_percent(stats.with_palette, total)})\n\n"
        f"<b>Хэштеги именно в промтах</b>\n"
        f"{_hashtag_lines(hashtags, limit=20)}"
    )


async def _capture_channel_post(
    message: Message,
    database: Database,
    analytics_channel_ids: frozenset[int],
    audit_logger: TelegramAuditLogger | None,
) -> None:
    if message.chat.id not in analytics_channel_ids:
        return
    try:
        parsed = await ingest_channel_post(database, message)
        logger.info(
            "Captured channel post channel=%s message=%s prompt=%s hashtags=%s",
            parsed.channel_id,
            parsed.message_id,
            parsed.prompt.is_prompt,
            len(parsed.hashtags),
        )
    except Exception as error:
        logger.exception("Failed to capture channel analytics post")
        if audit_logger is not None:
            await audit_logger.error(
                "Ошибка аналитики канала",
                error,
                channel_id=message.chat.id,
                message_id=message.message_id,
            )


@router.channel_post()
async def handle_channel_post(
    message: Message,
    database: Database,
    analytics_channel_ids: frozenset[int],
    audit_logger: TelegramAuditLogger | None = None,
) -> None:
    await _capture_channel_post(
        message,
        database,
        analytics_channel_ids,
        audit_logger,
    )


@router.edited_channel_post()
async def handle_edited_channel_post(
    message: Message,
    database: Database,
    analytics_channel_ids: frozenset[int],
    audit_logger: TelegramAuditLogger | None = None,
) -> None:
    await _capture_channel_post(
        message,
        database,
        analytics_channel_ids,
        audit_logger,
    )


@router.message(Command("channelstats", "stats"))
async def handle_channel_stats(
    message: Message,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    channel_id = _primary_channel_id(analytics_channel_ids)
    if channel_id is None:
        await message.answer("Каналы для аналитики не настроены.")
        return
    overview = await get_channel_overview(database, channel_id)
    if overview.total_messages == 0:
        await message.answer(
            "<b>Данных пока нет.</b>\n\n"
            f"Добавьте бота администратором канала <code>{channel_id}</code>. "
            "После этого новые и отредактированные посты начнут попадать в статистику."
        )
        return
    hashtags = await list_hashtag_stats(database, channel_id, limit=10)
    characters = await list_character_usage_stats(database, channel_id, limit=10)
    media_stats = await list_media_type_stats(database, channel_id)
    link_stats = await list_link_domain_stats(database, channel_id, limit=8)
    await message.answer(
        _overview_text(overview, hashtags, characters, media_stats, link_stats)
    )


@router.message(Command("promptstats"))
async def handle_prompt_stats(
    message: Message,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    channel_id = _primary_channel_id(analytics_channel_ids)
    if channel_id is None:
        await message.answer("Каналы для аналитики не настроены.")
        return
    stats = await get_prompt_structure_stats(database, channel_id)
    hashtags = await list_hashtag_stats(
        database,
        channel_id,
        limit=20,
        prompt_only=True,
    )
    await message.answer(_prompt_text(stats, hashtags))


@router.message(Command("hashtagstats", "tagstats"))
async def handle_hashtag_stats(
    message: Message,
    command: CommandObject,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    channel_id = _primary_channel_id(analytics_channel_ids)
    if channel_id is None:
        await message.answer("Каналы для аналитики не настроены.")
        return
    if command.args:
        item = await get_hashtag_stat(database, channel_id, command.args)
        if item is None:
            await message.answer("Такой хэштег пока не встречался в собранных постах.")
            return
        character = (
            f"\nПерсонаж в архиве: <b>{escape(item.character_name)}</b>"
            if item.character_name
            else "\nС карточкой персонажа пока не сопоставлен."
        )
        await message.answer(
            f"<b>#{escape(item.hashtag)}</b>\n\n"
            f"Публикаций: <b>{item.publication_count}</b>\n"
            f"Из них промтов: <b>{item.prompt_count}</b>\n"
            f"Последнее использование: <b>{_format_date(item.last_used_at)}</b>"
            f"{character}"
        )
        return

    items = await list_hashtag_stats(database, channel_id, limit=30)
    await message.answer(
        "<b>Хэштеги канала</b>\n\n"
        f"{_hashtag_lines(items, limit=30)}\n\n"
        "Подробно: <code>/tagstats #Аид</code>"
    )


@router.message(Command("characterstats"))
async def handle_character_stats(
    message: Message,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    channel_id = _primary_channel_id(analytics_channel_ids)
    if channel_id is None:
        await message.answer("Каналы для аналитики не настроены.")
        return
    items = await list_character_usage_stats(database, channel_id, limit=30)
    await message.answer(
        "<b>Персонажи, задействованные в канале</b>\n\n"
        f"{_character_lines(items, limit=30)}"
    )
