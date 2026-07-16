from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.channel_analytics import HashtagStat, get_hashtag_stat, list_hashtag_stats
from velvet_bot.database import Database
from velvet_bot.discussion_analytics import (
    DiscussionOverview,
    ParticipantStat,
    get_discussion_overview,
    list_participant_stats,
)
from velvet_bot.discussion_insights import RelinkResult, rebuild_discussion_threads
from velvet_bot.telegram_export_import import (
    ExportImportSummary,
    import_telegram_export,
    list_tracked_discussions,
    register_tracked_source,
)


@dataclass(frozen=True, slots=True)
class DiscussionRegistration:
    chat_id: int
    title: str | None
    username: str | None
    parent_channel_id: int


@dataclass(frozen=True, slots=True)
class DiscussionStats:
    chat_id: int
    overview: DiscussionOverview
    participants: tuple[ParticipantStat, ...]
    hashtags: tuple[HashtagStat, ...]


@dataclass(frozen=True, slots=True)
class ImportResult:
    summary: ExportImportSummary
    relink: RelinkResult | None


def primary_channel_id(channel_ids: frozenset[int]) -> int | None:
    return sorted(channel_ids)[0] if channel_ids else None


async def load_hashtag_stats(
    database: Database,
    channel_ids: frozenset[int],
    value: str,
) -> HashtagStat | tuple[HashtagStat, ...]:
    channel_id = primary_channel_id(channel_ids)
    if channel_id is None:
        raise ValueError("Каналы для аналитики не настроены.")
    cleaned = value.strip()
    if cleaned:
        item = await get_hashtag_stat(database, channel_id, cleaned)
        if item is None:
            raise ValueError("Такой хэштег пока не встречался в собранных постах.")
        return item
    return tuple(await list_hashtag_stats(database, channel_id, limit=30))


async def register_discussion(
    database: Database,
    channel_ids: frozenset[int],
    *,
    chat_id: int,
    title: str | None,
    username: str | None,
) -> DiscussionRegistration:
    parent_channel_id = primary_channel_id(channel_ids)
    if parent_channel_id is None:
        raise ValueError("Основной канал аналитики не настроен.")
    await register_tracked_source(
        database,
        chat_id=chat_id,
        title=title,
        username=username,
        source_kind="discussion",
        parent_channel_id=parent_channel_id,
    )
    return DiscussionRegistration(
        chat_id=chat_id,
        title=title,
        username=username,
        parent_channel_id=parent_channel_id,
    )


async def load_discussion_stats(
    database: Database,
    channel_ids: frozenset[int],
    raw_chat_id: str | None,
) -> DiscussionStats:
    parent_channel_id = primary_channel_id(channel_ids)
    if raw_chat_id and raw_chat_id.strip():
        try:
            chat_id = int(raw_chat_id.strip())
        except ValueError as error:
            raise ValueError("Chat ID должен быть числом.") from error
    else:
        discussions = await list_tracked_discussions(
            database,
            parent_channel_id=parent_channel_id,
        )
        if not discussions:
            raise ValueError(
                "Чат обсуждений ещё не подключён. Запустите подключение внутри него."
            )
        chat_id = discussions[0][0]

    return DiscussionStats(
        chat_id=chat_id,
        overview=await get_discussion_overview(database, chat_id),
        participants=tuple(await list_participant_stats(database, chat_id, limit=15)),
        hashtags=tuple(await list_hashtag_stats(database, chat_id, limit=15)),
    )


async def import_export_payload(
    database: Database,
    channel_ids: frozenset[int],
    *,
    raw: bytes,
    file_name: str,
    source_kind: str,
    target_chat_value: str | None,
    imported_by: int | None,
) -> ImportResult:
    if source_kind not in {"channel", "discussion"}:
        raise ValueError("Неизвестный тип источника импорта.")
    parent_channel_id = primary_channel_id(channel_ids)
    target_chat_id: int | None = parent_channel_id if source_kind == "channel" else None
    if source_kind == "discussion" and target_chat_value and target_chat_value.strip():
        try:
            target_chat_id = int(target_chat_value.strip())
        except ValueError as error:
            raise ValueError("ID обсуждения должен быть числом.") from error

    summary = await import_telegram_export(
        database,
        raw=raw,
        file_name=file_name,
        source_kind=source_kind,
        target_chat_id=target_chat_id,
        parent_channel_id=(parent_channel_id if source_kind == "discussion" else None),
        imported_by=imported_by,
    )
    relink = (
        await rebuild_discussion_threads(database, summary.source_chat_id)
        if source_kind == "discussion"
        else None
    )
    return ImportResult(summary=summary, relink=relink)


__all__ = (
    "DiscussionRegistration",
    "DiscussionStats",
    "ImportResult",
    "import_export_payload",
    "load_discussion_stats",
    "load_hashtag_stats",
    "primary_channel_id",
    "register_discussion",
)
