from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from velvet_bot.channel_analytics import (
    analyze_prompt_text,
    compact_identity,
    extract_hashtags,
    extract_links,
)
from velvet_bot.database import Database

MAX_JSON_BYTES = 64 * 1024 * 1024
_ALLOWED_SOURCE_KINDS = frozenset({"channel", "discussion"})
_HEX_TAG_RE = re.compile(r"^[a-f0-9]{6}$")


@dataclass(frozen=True, slots=True)
class ExportImportSummary:
    source_chat_id: int
    source_kind: str
    source_name: str
    total_records: int
    imported_messages: int
    publication_count: int
    prompt_publications: int
    hashtag_count: int
    character_matches: int
    reaction_count: int
    duplicate_import: bool
    file_sha256: str


@dataclass(frozen=True, slots=True)
class ExportRecord:
    message_id: int
    publication_key: str
    posted_at: datetime
    edited_at: datetime | None
    sender_id: str | None
    sender_name: str | None
    text_content: str
    media_type: str
    has_spoiler: bool
    reply_to_message_id: int | None
    topic_id: int | None
    reactions_total: int
    reaction_breakdown: dict[str, int]


def flatten_export_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return "" if value is None else str(value)

    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(str(item.get("text", "")))
    return "".join(parts)


def _load_json_bytes(raw: bytes, file_name: str) -> bytes:
    lowered = file_name.casefold()
    if lowered.endswith(".json"):
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("JSON экспорта слишком большой.")
        return raw

    if not lowered.endswith(".zip"):
        raise ValueError("Нужен result.json или ZIP экспорта Telegram Desktop.")

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if name.casefold().endswith("result.json")
                and not name.endswith("/")
            ]
            if not candidates:
                raise ValueError("В ZIP не найден result.json.")
            candidate = min(candidates, key=lambda name: (name.count("/"), len(name)))
            info = archive.getinfo(candidate)
            if info.file_size > MAX_JSON_BYTES:
                raise ValueError("result.json внутри ZIP слишком большой.")
            return archive.read(candidate)
    except zipfile.BadZipFile as error:
        raise ValueError("Файл не является корректным ZIP-архивом.") from error


def load_export_payload(raw: bytes, file_name: str) -> dict[str, Any]:
    payload_bytes = _load_json_bytes(raw, file_name)
    try:
        payload = json.loads(payload_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Не удалось прочитать result.json экспорта Telegram.") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise ValueError("В JSON отсутствует список messages.")
    return payload


def infer_export_chat_id(payload: dict[str, Any]) -> int:
    try:
        raw_id = int(payload["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("В экспорте отсутствует корректный ID чата.") from error

    if raw_id < 0:
        return raw_id
    export_type = str(payload.get("type", "")).casefold()
    if export_type in {
        "public_channel",
        "private_channel",
        "supergroup",
        "private_supergroup",
    }:
        return -(1_000_000_000_000 + raw_id)
    return -raw_id


def _parse_datetime(item: dict[str, Any], key: str, unix_key: str) -> datetime | None:
    raw_unix = item.get(unix_key)
    if raw_unix not in (None, ""):
        try:
            return datetime.fromtimestamp(int(raw_unix), tz=UTC)
        except (TypeError, ValueError, OSError):
            pass

    raw_value = item.get(key)
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw_value))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def _detect_export_media_type(item: dict[str, Any]) -> str:
    if item.get("photo"):
        return "photo"
    media_type = str(item.get("media_type", "")).casefold()
    if media_type in {"video_file", "video_message"}:
        return "video"
    if media_type in {"animation", "gif"}:
        return "animation"
    if media_type in {"voice_message", "audio_file"}:
        return "audio"
    if item.get("file"):
        return "document"
    if item.get("sticker"):
        return "sticker"
    if item.get("poll"):
        return "poll"
    return "text"


def _reaction_breakdown(item: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    reactions = item.get("reactions")
    if not isinstance(reactions, list):
        return result
    for reaction in reactions:
        if not isinstance(reaction, dict):
            continue
        label = str(
            reaction.get("emoji")
            or reaction.get("document_id")
            or reaction.get("type")
            or "unknown"
        )
        try:
            count = int(reaction.get("count", 0))
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            result[label] = result.get(label, 0) + count
    return result


def _is_media_message(item: dict[str, Any]) -> bool:
    return _detect_export_media_type(item) != "text"


def _publication_groups(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_key: tuple[str, str] | None = None

    for item in messages:
        if item.get("type") != "message":
            continue
        is_media = _is_media_message(item)
        key = (
            str(item.get("date_unixtime") or item.get("date") or ""),
            str(item.get("from_id") or item.get("actor_id") or ""),
        )
        if current and is_media and current_key == key and all(
            _is_media_message(existing) for existing in current
        ):
            current.append(item)
            continue
        if current:
            groups.append(current)
        current = [item]
        current_key = key if is_media else None

    if current:
        groups.append(current)
    return groups


def parse_export_records(payload: dict[str, Any]) -> list[ExportRecord]:
    raw_messages = [
        item for item in payload.get("messages", []) if isinstance(item, dict)
    ]
    records: list[ExportRecord] = []
    for group in _publication_groups(raw_messages):
        first_id = int(group[0].get("id", 0))
        publication_key = (
            f"export-album:{first_id}"
            if len(group) > 1
            else f"export-message:{first_id}"
        )
        for item in group:
            posted_at = _parse_datetime(item, "date", "date_unixtime")
            if posted_at is None:
                continue
            reactions = _reaction_breakdown(item)
            reply_to = item.get("reply_to_message_id")
            topic_id = item.get("topic_id") or item.get("message_thread_id")
            records.append(
                ExportRecord(
                    message_id=int(item.get("id", 0)),
                    publication_key=publication_key,
                    posted_at=posted_at,
                    edited_at=_parse_datetime(item, "edited", "edited_unixtime"),
                    sender_id=(
                        str(item.get("from_id")) if item.get("from_id") else None
                    ),
                    sender_name=(
                        str(item.get("from")) if item.get("from") else None
                    ),
                    text_content=flatten_export_text(item.get("text")),
                    media_type=_detect_export_media_type(item),
                    has_spoiler=bool(item.get("media_spoiler")),
                    reply_to_message_id=(int(reply_to) if reply_to is not None else None),
                    topic_id=(int(topic_id) if topic_id is not None else None),
                    reactions_total=sum(reactions.values()),
                    reaction_breakdown=reactions,
                )
            )
    return records


async def register_tracked_source(
    database: Database,
    *,
    chat_id: int,
    title: str | None,
    username: str | None,
    source_kind: str,
    parent_channel_id: int | None = None,
) -> None:
    if source_kind not in _ALLOWED_SOURCE_KINDS:
        raise ValueError("Неизвестный тип источника аналитики.")
    async with database.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO tracked_channels (
                chat_id, title, username, enabled, source_kind,
                parent_channel_id, updated_at
            )
            VALUES ($1, $2, $3, TRUE, $4, $5, NOW())
            ON CONFLICT (chat_id) DO UPDATE
            SET title = COALESCE(EXCLUDED.title, tracked_channels.title),
                username = COALESCE(EXCLUDED.username, tracked_channels.username),
                enabled = TRUE,
                source_kind = EXCLUDED.source_kind,
                parent_channel_id = EXCLUDED.parent_channel_id,
                updated_at = NOW()
            """,
            chat_id,
            title,
            username,
            source_kind,
            parent_channel_id,
        )


async def is_tracked_discussion(database: Database, chat_id: int) -> bool:
    async with database.acquire() as connection:
        return bool(
            await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM tracked_channels
                    WHERE chat_id = $1
                      AND source_kind = 'discussion'
                      AND enabled = TRUE
                )
                """,
                chat_id,
            )
        )


async def list_tracked_discussions(
    database: Database,
    *,
    parent_channel_id: int | None = None,
) -> list[tuple[int, str | None]]:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT chat_id, title
            FROM tracked_channels
            WHERE source_kind = 'discussion'
              AND enabled = TRUE
              AND ($1::BIGINT IS NULL OR parent_channel_id = $1)
            ORDER BY title NULLS LAST, chat_id
            """,
            parent_channel_id,
        )
    return [(int(row["chat_id"]), row["title"]) for row in rows]


async def import_telegram_export(
    database: Database,
    *,
    raw: bytes,
    file_name: str,
    source_kind: str,
    target_chat_id: int | None = None,
    parent_channel_id: int | None = None,
    imported_by: int | None = None,
) -> ExportImportSummary:
    if source_kind not in _ALLOWED_SOURCE_KINDS:
        raise ValueError("Тип импорта должен быть channel или discussion.")

    payload = load_export_payload(raw, file_name)
    source_chat_id = target_chat_id or infer_export_chat_id(payload)
    source_name = str(payload.get("name") or "Telegram export")
    records = parse_export_records(payload)
    digest = hashlib.sha256(raw).hexdigest()

    async with database.acquire() as connection:
        duplicate = await connection.fetchrow(
            """
            SELECT imported_messages, publication_count, metadata
            FROM telegram_export_imports
            WHERE file_sha256 = $1
            """,
            digest,
        )
        if duplicate is not None:
            metadata = duplicate["metadata"] or {}
            return ExportImportSummary(
                source_chat_id=source_chat_id,
                source_kind=source_kind,
                source_name=source_name,
                total_records=len(payload.get("messages", [])),
                imported_messages=int(duplicate["imported_messages"] or 0),
                publication_count=int(duplicate["publication_count"] or 0),
                prompt_publications=int(metadata.get("prompt_publications", 0)),
                hashtag_count=int(metadata.get("hashtag_count", 0)),
                character_matches=int(metadata.get("character_matches", 0)),
                reaction_count=int(metadata.get("reaction_count", 0)),
                duplicate_import=True,
                file_sha256=digest,
            )

        character_rows = await connection.fetch(
            "SELECT id, name, normalized_name FROM characters"
        )
        character_by_alias = {
            compact_identity(str(row["normalized_name"])): int(row["id"])
            for row in character_rows
        }

        prompt_publications: set[str] = set()
        all_hashtags: set[tuple[str, str]] = set()
        matched_characters: set[int] = set()
        reaction_count = 0

        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO tracked_channels (
                    chat_id, title, enabled, source_kind,
                    parent_channel_id, last_post_at, updated_at
                )
                VALUES ($1, $2, TRUE, $3, $4, $5, NOW())
                ON CONFLICT (chat_id) DO UPDATE
                SET title = EXCLUDED.title,
                    enabled = TRUE,
                    source_kind = EXCLUDED.source_kind,
                    parent_channel_id = EXCLUDED.parent_channel_id,
                    last_post_at = GREATEST(
                        tracked_channels.last_post_at,
                        EXCLUDED.last_post_at
                    ),
                    updated_at = NOW()
                """,
                source_chat_id,
                source_name,
                source_kind,
                parent_channel_id,
                max((record.posted_at for record in records), default=None),
            )

            for record in records:
                prompt = analyze_prompt_text(record.text_content)
                if prompt.is_prompt:
                    prompt_publications.add(record.publication_key)
                reaction_count += record.reactions_total

                post_id = await connection.fetchval(
                    """
                    INSERT INTO channel_posts (
                        channel_id, message_id, publication_key, posted_at,
                        edited_at, author_signature, text_content, text_length,
                        media_type, has_spoiler, is_prompt, prompt_score,
                        has_important_section, has_strict_section,
                        has_negative_section, has_technical_section, has_palette,
                        sender_id, sender_name, reply_to_message_id, topic_id,
                        reactions_total, reaction_breakdown,
                        imported_from_export, updated_at
                    )
                    VALUES (
                        $1, $2, $3, $4,
                        $5, $6, $7, $8,
                        $9, $10, $11, $12,
                        $13, $14,
                        $15, $16, $17,
                        $18, $19, $20, $21,
                        $22, $23::JSONB,
                        TRUE, NOW()
                    )
                    ON CONFLICT (channel_id, message_id) DO UPDATE
                    SET publication_key = EXCLUDED.publication_key,
                        posted_at = EXCLUDED.posted_at,
                        edited_at = EXCLUDED.edited_at,
                        author_signature = EXCLUDED.author_signature,
                        text_content = EXCLUDED.text_content,
                        text_length = EXCLUDED.text_length,
                        media_type = EXCLUDED.media_type,
                        has_spoiler = EXCLUDED.has_spoiler,
                        is_prompt = EXCLUDED.is_prompt,
                        prompt_score = EXCLUDED.prompt_score,
                        has_important_section = EXCLUDED.has_important_section,
                        has_strict_section = EXCLUDED.has_strict_section,
                        has_negative_section = EXCLUDED.has_negative_section,
                        has_technical_section = EXCLUDED.has_technical_section,
                        has_palette = EXCLUDED.has_palette,
                        sender_id = EXCLUDED.sender_id,
                        sender_name = EXCLUDED.sender_name,
                        reply_to_message_id = EXCLUDED.reply_to_message_id,
                        topic_id = EXCLUDED.topic_id,
                        reactions_total = EXCLUDED.reactions_total,
                        reaction_breakdown = EXCLUDED.reaction_breakdown,
                        imported_from_export = TRUE,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    source_chat_id,
                    record.message_id,
                    record.publication_key,
                    record.posted_at,
                    record.edited_at,
                    record.sender_name,
                    record.text_content,
                    len(record.text_content),
                    record.media_type,
                    record.has_spoiler,
                    prompt.is_prompt,
                    prompt.score,
                    prompt.has_important,
                    prompt.has_strict,
                    prompt.has_negative,
                    prompt.has_technical,
                    prompt.has_palette,
                    record.sender_id,
                    record.sender_name,
                    record.reply_to_message_id,
                    record.topic_id,
                    record.reactions_total,
                    json.dumps(record.reaction_breakdown, ensure_ascii=False),
                )
                if post_id is None:
                    continue

                await connection.execute(
                    "DELETE FROM channel_post_hashtags WHERE post_id = $1",
                    post_id,
                )
                await connection.execute(
                    "DELETE FROM channel_post_links WHERE post_id = $1",
                    post_id,
                )

                for display, normalized in extract_hashtags(record.text_content):
                    if _HEX_TAG_RE.fullmatch(normalized):
                        continue
                    character_id = character_by_alias.get(compact_identity(normalized))
                    all_hashtags.add((record.publication_key, normalized))
                    if character_id is not None:
                        matched_characters.add(character_id)
                    await connection.execute(
                        """
                        INSERT INTO channel_post_hashtags (
                            post_id, hashtag, normalized_hashtag,
                            character_id, is_character
                        )
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (post_id, normalized_hashtag) DO UPDATE
                        SET hashtag = EXCLUDED.hashtag,
                            character_id = EXCLUDED.character_id,
                            is_character = EXCLUDED.is_character
                        """,
                        post_id,
                        display,
                        normalized,
                        character_id,
                        character_id is not None,
                    )

                for url, domain, is_telegram in extract_links(record.text_content):
                    await connection.execute(
                        """
                        INSERT INTO channel_post_links (
                            post_id, url, domain, is_telegram
                        )
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (post_id, url) DO UPDATE
                        SET domain = EXCLUDED.domain,
                            is_telegram = EXCLUDED.is_telegram
                        """,
                        post_id,
                        url,
                        domain,
                        is_telegram,
                    )

            publication_count = len({record.publication_key for record in records})
            metadata = {
                "source_name": source_name,
                "prompt_publications": len(prompt_publications),
                "hashtag_count": len(all_hashtags),
                "character_matches": len(matched_characters),
                "reaction_count": reaction_count,
            }
            await connection.execute(
                """
                INSERT INTO telegram_export_imports (
                    file_sha256, file_name, source_chat_id, source_kind,
                    parent_channel_id, imported_by, total_records,
                    imported_messages, publication_count, finished_at, metadata
                )
                VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7,
                    $8, $9, NOW(), $10::JSONB
                )
                """,
                digest,
                Path(file_name).name,
                source_chat_id,
                source_kind,
                parent_channel_id,
                imported_by,
                len(payload.get("messages", [])),
                len(records),
                publication_count,
                json.dumps(metadata, ensure_ascii=False),
            )

    return ExportImportSummary(
        source_chat_id=source_chat_id,
        source_kind=source_kind,
        source_name=source_name,
        total_records=len(payload.get("messages", [])),
        imported_messages=len(records),
        publication_count=len({record.publication_key for record in records}),
        prompt_publications=len(prompt_publications),
        hashtag_count=len(all_hashtags),
        character_matches=len(matched_characters),
        reaction_count=reaction_count,
        duplicate_import=False,
        file_sha256=digest,
    )
