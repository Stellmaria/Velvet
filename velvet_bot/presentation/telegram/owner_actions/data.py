from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.types import Message

from velvet_bot.application.owner_analytics import (
    DiscussionStats,
    load_discussion_stats,
    load_hashtag_stats,
    register_discussion,
)
from velvet_bot.application.owner_profiles import (
    add_alias_from_text,
    delete_alias_from_text,
    list_aliases_from_text,
)
from velvet_bot.channel_analytics import HashtagStat
from velvet_bot.database import Database


DATA_ACTIONS = frozenset(
    {
        "aliasadd",
        "aliases",
        "aliasdel",
        "tagstats",
        "trackdiscussion",
        "discussionstats",
    }
)


def _format_date(value) -> str:
    return value.astimezone().strftime("%d.%m.%Y") if value else "—"


def _discussion_text(result: DiscussionStats) -> str:
    overview = result.overview
    participants = "\n".join(
        f"• <b>{escape(item.sender_name)}</b> — {item.message_count} сообщений, "
        f"ответов {item.reply_count}, медиа {item.media_count}"
        for item in result.participants
    ) or "• данных пока нет"
    hashtags = "\n".join(
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
        f"Реакций: <b>{overview.total_reactions}</b>\n\n"
        f"<b>Активные участники</b>\n{participants}\n\n"
        f"<b>Частые хэштеги</b>\n{hashtags}"
    )


def _hashtag_text(item: HashtagStat) -> str:
    character = (
        f"\nПерсонаж в архиве: <b>{escape(item.character_name)}</b>"
        if item.character_name
        else "\nС карточкой персонажа пока не сопоставлен."
    )
    return (
        f"<b>#{escape(item.hashtag)}</b>\n\n"
        f"Публикаций: <b>{item.publication_count}</b>\n"
        f"Из них промтов: <b>{item.prompt_count}</b>\n"
        f"Последнее использование: <b>{_format_date(item.last_used_at)}</b>"
        f"{character}"
    )


async def handle_owner_data_action(
    *,
    message: Message,
    owner_action: str,
    value: str,
    database: Database,
    bot: Bot,
    analytics_channel_ids: frozenset[int],
    actor_id: int | None,
) -> bool:
    if owner_action not in DATA_ACTIONS:
        return False

    if owner_action == "aliasadd":
        item = await add_alias_from_text(database, value, actor_id=actor_id)
        await message.answer(
            f"Алиас <code>#{escape(item.alias)}</code> назначен персонажу "
            f"<b>{escape(item.character_name)}</b>."
        )
        return True

    if owner_action == "aliases":
        character, items = await list_aliases_from_text(database, value)
        lines = [
            f"• <code>#{escape(item.alias)}</code>"
            + (" · основное имя" if item.source == "name" else "")
            for item in items
        ] or ["• алиасов пока нет"]
        await message.answer(
            f"<b>Алиасы: {escape(character.name)}</b>\n\n" + "\n".join(lines)
        )
        return True

    if owner_action == "aliasdel":
        result = await delete_alias_from_text(database, value)
        if not result.deleted:
            raise ValueError(
                "Алиас не найден или это основное имя персонажа, которое удалять нельзя."
            )
        await message.answer(
            f"Алиас <code>#{escape(result.alias)}</code> удалён у "
            f"<b>{escape(result.character.name)}</b>."
        )
        return True

    if owner_action == "tagstats":
        result = await load_hashtag_stats(database, analytics_channel_ids, value)
        if isinstance(result, HashtagStat):
            await message.answer(_hashtag_text(result))
        else:
            lines = [
                f"• <code>#{escape(item.hashtag)}</code> — "
                f"<b>{item.publication_count}</b> публикаций"
                for item in result
            ] or ["• пока нет данных"]
            await message.answer("<b>Хэштеги канала</b>\n\n" + "\n".join(lines))
        return True

    if owner_action == "trackdiscussion":
        try:
            chat_id = int(value)
        except ValueError as error:
            raise ValueError("Chat ID должен быть числом.") from error
        chat = await bot.get_chat(chat_id)
        result = await register_discussion(
            database,
            analytics_channel_ids,
            chat_id=chat_id,
            title=chat.title,
            username=chat.username,
        )
        await message.answer(
            "<b>Чат обсуждений подключён.</b>\n\n"
            f"Название: <b>{escape(result.title or 'без названия')}</b>\n"
            f"Chat ID: <code>{result.chat_id}</code>\n"
            f"Связан с каналом: <code>{result.parent_channel_id}</code>"
        )
        return True

    result = await load_discussion_stats(
        database,
        analytics_channel_ids,
        None if value.casefold() == "основной" else value,
    )
    await message.answer(_discussion_text(result))
    return True


__all__ = ("DATA_ACTIONS", "handle_owner_data_action")
