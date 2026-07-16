from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram.types import Message

from velvet_bot.channel_analytics import (
    analyze_prompt_text,
    compact_identity,
    extract_hashtags,
    extract_links,
)
from velvet_bot.database import Database
from velvet_bot.media import extract_media
from velvet_bot.post_classification import classify_post

TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
MEDIA_GROUP_LIMIT = 10
_STORY_REQUIRED_UNIVERSES = frozenset({"shs", "kr", "lm", "idm", "lagerta"})
_ADULT_RE = re.compile(
    r"(?:^|[^\w])(?:18\+|nsfw|art\s*nude|nude|ню|обнаж|эрот|без\s+одежд)",
    re.IGNORECASE,
)
_URL_CANDIDATE_RE = re.compile(r"(?:https?://|t\.me/)[^\s<>]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PublicationIssue:
    code: str
    severity: str
    title: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class PublicationItem:
    id: int
    draft_id: int
    position: int
    telegram_file_id: str
    telegram_file_unique_id: str | None
    media_type: str
    mime_type: str | None
    file_name: str | None
    file_size: int | None
    source_message_id: int | None
    has_spoiler: bool


@dataclass(frozen=True, slots=True)
class PublicationDraft:
    id: int
    owner_id: int
    target_chat_id: int
    source_chat_id: int | None
    source_message_id: int | None
    source_media_group_id: str | None
    text_content: str
    status: str
    post_type: str
    has_spoiler: bool
    content_hash: str
    validation_status: str
    validation_error_count: int
    validation_warning_count: int
    validation_report: tuple[PublicationIssue, ...]
    scheduled_at: datetime | None
    published_at: datetime | None
    published_message_ids: tuple[int, ...]
    attempt_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    items: tuple[PublicationItem, ...]


@dataclass(frozen=True, slots=True)
class PublicationDraftPage:
    items: tuple[PublicationDraft, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


def _message_text(message: Message) -> str:
    return message.text or message.caption or ""


def _content_hash(text: str, unique_ids: list[str]) -> str:
    normalized_text = unicodedata.normalize("NFKC", text).strip()
    payload = "\n".join([normalized_text, *sorted(unique_ids)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _row_to_issue(value: Any) -> PublicationIssue:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    value = value if isinstance(value, dict) else {}
    return PublicationIssue(
        code=str(value.get("code", "unknown")),
        severity=str(value.get("severity", "warning")),
        title=str(value.get("title", "Проверка")),
        detail=str(value.get("detail", "")),
    )


def _row_to_item(row) -> PublicationItem:
    return PublicationItem(
        id=int(row["id"]),
        draft_id=int(row["draft_id"]),
        position=int(row["position"]),
        telegram_file_id=str(row["telegram_file_id"]),
        telegram_file_unique_id=row["telegram_file_unique_id"],
        media_type=str(row["media_type"]),
        mime_type=row["mime_type"],
        file_name=row["file_name"],
        file_size=(int(row["file_size"]) if row["file_size"] is not None else None),
        source_message_id=row["source_message_id"],
        has_spoiler=bool(row["has_spoiler"]),
    )


def _row_to_draft(row, item_rows) -> PublicationDraft:
    raw_report = row["validation_report"] or []
    if isinstance(raw_report, str):
        try:
            raw_report = json.loads(raw_report)
        except json.JSONDecodeError:
            raw_report = []
    return PublicationDraft(
        id=int(row["id"]),
        owner_id=int(row["owner_id"]),
        target_chat_id=int(row["target_chat_id"]),
        source_chat_id=row["source_chat_id"],
        source_message_id=row["source_message_id"],
        source_media_group_id=row["source_media_group_id"],
        text_content=str(row["text_content"] or ""),
        status=str(row["status"]),
        post_type=str(row["post_type"]),
        has_spoiler=bool(row["has_spoiler"]),
        content_hash=str(row["content_hash"]),
        validation_status=str(row["validation_status"]),
        validation_error_count=int(row["validation_error_count"] or 0),
        validation_warning_count=int(row["validation_warning_count"] or 0),
        validation_report=tuple(_row_to_issue(value) for value in raw_report),
        scheduled_at=row["scheduled_at"],
        published_at=row["published_at"],
        published_message_ids=tuple(int(value) for value in (row["published_message_ids"] or [])),
        attempt_count=int(row["attempt_count"] or 0),
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        items=tuple(_row_to_item(item) for item in item_rows),
    )


async def capture_publication_inbox(
    database: Database,
    message: Message,
    *,
    owner_id: int,
) -> None:
    media = extract_media(message)
    text_content = _message_text(message)
    if media is None and not text_content:
        return
    async with database._require_pool().acquire() as connection:
        await connection.execute(
            """
            INSERT INTO publication_inbox_items (
                owner_id, source_chat_id, source_message_id, media_group_id,
                text_content, telegram_file_id, telegram_file_unique_id,
                media_type, mime_type, file_name, file_size, has_spoiler,
                received_at
            )
            VALUES (
                $1, $2, $3, $4,
                $5, $6, $7,
                $8, $9, $10, $11, $12,
                NOW()
            )
            ON CONFLICT (owner_id, source_chat_id, source_message_id) DO UPDATE
            SET media_group_id = EXCLUDED.media_group_id,
                text_content = EXCLUDED.text_content,
                telegram_file_id = EXCLUDED.telegram_file_id,
                telegram_file_unique_id = EXCLUDED.telegram_file_unique_id,
                media_type = EXCLUDED.media_type,
                mime_type = EXCLUDED.mime_type,
                file_name = EXCLUDED.file_name,
                file_size = EXCLUDED.file_size,
                has_spoiler = EXCLUDED.has_spoiler,
                received_at = NOW()
            """,
            owner_id,
            message.chat.id,
            message.message_id,
            str(message.media_group_id) if message.media_group_id else None,
            text_content,
            media.telegram_file_id if media else None,
            media.telegram_file_unique_id if media else None,
            media.media_type if media else "text",
            media.mime_type if media else None,
            media.original_file_name if media else None,
            media.file_size if media else None,
            bool(getattr(message, "has_media_spoiler", False)),
        )


async def create_draft_from_message(
    database: Database,
    message: Message,
    *,
    owner_id: int,
    target_chat_id: int,
) -> PublicationDraft:
    await capture_publication_inbox(database, message, owner_id=owner_id)
    group_id = str(message.media_group_id) if message.media_group_id else None
    async with database._require_pool().acquire() as connection:
        if group_id:
            rows = await connection.fetch(
                """
                SELECT *
                FROM publication_inbox_items
                WHERE owner_id = $1
                  AND source_chat_id = $2
                  AND media_group_id = $3
                ORDER BY source_message_id
                """,
                owner_id,
                message.chat.id,
                group_id,
            )
        else:
            rows = await connection.fetch(
                """
                SELECT *
                FROM publication_inbox_items
                WHERE owner_id = $1
                  AND source_chat_id = $2
                  AND source_message_id = $3
                """,
                owner_id,
                message.chat.id,
                message.message_id,
            )
        if not rows:
            raise ValueError("Сообщение для черновика не найдено.")

        text_parts: list[str] = []
        for row in rows:
            value = str(row["text_content"] or "").strip()
            if value and value not in text_parts:
                text_parts.append(value)
        text_content = "\n\n".join(text_parts)
        unique_ids = [
            str(row["telegram_file_unique_id"])
            for row in rows
            if row["telegram_file_unique_id"]
        ]
        digest = _content_hash(text_content, unique_ids)
        prompt = analyze_prompt_text(text_content)
        hashtags = extract_hashtags(text_content)
        media_type = next(
            (str(row["media_type"]) for row in rows if row["telegram_file_id"]),
            "text",
        )
        classification = classify_post(
            text_content,
            hashtags,
            is_prompt=prompt.is_prompt,
            media_type=media_type,
        )
        async with connection.transaction():
            draft_id = await connection.fetchval(
                """
                INSERT INTO publication_drafts (
                    owner_id, target_chat_id, source_chat_id, source_message_id,
                    source_media_group_id, text_content, status, post_type,
                    has_spoiler, content_hash, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, 'draft', $7, $8, $9, NOW())
                RETURNING id
                """,
                owner_id,
                target_chat_id,
                message.chat.id,
                message.message_id,
                group_id,
                text_content,
                classification.post_type,
                any(bool(row["has_spoiler"]) for row in rows),
                digest,
            )
            if draft_id is None:
                raise RuntimeError("Не удалось создать черновик.")
            position = 0
            for row in rows:
                if not row["telegram_file_id"]:
                    continue
                await connection.execute(
                    """
                    INSERT INTO publication_draft_items (
                        draft_id, position, telegram_file_id,
                        telegram_file_unique_id, media_type, mime_type,
                        file_name, file_size, source_message_id, has_spoiler
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    draft_id,
                    position,
                    row["telegram_file_id"],
                    row["telegram_file_unique_id"],
                    row["media_type"],
                    row["mime_type"],
                    row["file_name"],
                    row["file_size"],
                    row["source_message_id"],
                    row["has_spoiler"],
                )
                position += 1
            await _log_event(
                connection,
                int(draft_id),
                "created",
                owner_id,
                {"source_message_id": message.message_id},
            )
    draft = await get_publication_draft(database, int(draft_id), owner_id=owner_id)
    if draft is None:
        raise RuntimeError("Созданный черновик не найден.")
    return await validate_publication_draft(database, draft.id, owner_id=owner_id)


async def _log_event(connection, draft_id: int, event_type: str, actor_id: int | None, details: dict[str, Any]) -> None:
    await connection.execute(
        """
        INSERT INTO publication_events (draft_id, event_type, actor_id, details)
        VALUES ($1, $2, $3, $4::JSONB)
        """,
        draft_id,
        event_type,
        actor_id,
        json.dumps(details, ensure_ascii=False),
    )


async def get_publication_draft(
    database: Database,
    draft_id: int,
    *,
    owner_id: int | None = None,
) -> PublicationDraft | None:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT *
            FROM publication_drafts
            WHERE id = $1
              AND ($2::BIGINT IS NULL OR owner_id = $2)
            """,
            draft_id,
            owner_id,
        )
        if row is None:
            return None
        item_rows = await connection.fetch(
            """
            SELECT *
            FROM publication_draft_items
            WHERE draft_id = $1
            ORDER BY position
            """,
            draft_id,
        )
    return _row_to_draft(row, item_rows)


async def list_publication_drafts(
    database: Database,
    *,
    owner_id: int,
    statuses: tuple[str, ...],
    page: int = 0,
    page_size: int = 6,
) -> PublicationDraftPage:
    safe_size = max(1, min(page_size, 10))
    safe_page = max(0, page)
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM publication_drafts
                WHERE owner_id = $1
                  AND status = ANY($2::VARCHAR[])
                """,
                owner_id,
                list(statuses),
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT *
            FROM publication_drafts
            WHERE owner_id = $1
              AND status = ANY($2::VARCHAR[])
            ORDER BY COALESCE(scheduled_at, updated_at) DESC, id DESC
            OFFSET $3 LIMIT $4
            """,
            owner_id,
            list(statuses),
            normalized_page * safe_size,
            safe_size,
        )
        result: list[PublicationDraft] = []
        for row in rows:
            item_rows = await connection.fetch(
                "SELECT * FROM publication_draft_items WHERE draft_id = $1 ORDER BY position",
                int(row["id"]),
            )
            result.append(_row_to_draft(row, item_rows))
    return PublicationDraftPage(tuple(result), normalized_page, safe_size, total)


async def validate_publication_draft(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
) -> PublicationDraft:
    draft = await get_publication_draft(database, draft_id, owner_id=owner_id)
    if draft is None:
        raise ValueError("Черновик не найден.")

    text = draft.text_content.strip()
    hashtags = extract_hashtags(text)
    prompt = analyze_prompt_text(text)
    media_type = draft.items[0].media_type if draft.items else "text"
    classification = classify_post(
        text,
        hashtags,
        is_prompt=prompt.is_prompt,
        media_type=media_type,
    )
    issues: list[PublicationIssue] = []

    if not text and not draft.items:
        issues.append(PublicationIssue("empty", "error", "Пустой пост", "Нет текста и медиа."))
    if not draft.items and len(text) > TEXT_LIMIT:
        issues.append(
            PublicationIssue(
                "text_limit",
                "error",
                "Превышен лимит текста",
                f"{len(text)} из {TEXT_LIMIT} символов.",
            )
        )
    if draft.items and len(text) > CAPTION_LIMIT:
        issues.append(
            PublicationIssue(
                "caption_split",
                "warning",
                "Текст длиннее подписи к медиа",
                f"{len(text)} символов. Бот отправит текст отдельно, затем медиа.",
            )
        )
    if len(draft.items) > MEDIA_GROUP_LIMIT:
        issues.append(
            PublicationIssue(
                "media_count",
                "error",
                "Слишком большой альбом",
                f"{len(draft.items)} файлов, допустимо не более {MEDIA_GROUP_LIMIT}.",
            )
        )
    if len(draft.items) > 1:
        types = {item.media_type for item in draft.items}
        if "animation" in types:
            issues.append(
                PublicationIssue(
                    "album_animation",
                    "error",
                    "Анимация в альбоме",
                    "Telegram не принимает animation в sendMediaGroup.",
                )
            )
        if "document" in types and types != {"document"}:
            issues.append(
                PublicationIssue(
                    "album_mixed_document",
                    "error",
                    "Несовместимые типы альбома",
                    "Документы нельзя смешивать с фото или видео в одном альбоме.",
                )
            )

    tag_keys = [compact_identity(normalized) for _, normalized in hashtags]
    character_rows = []
    unresolved: list[str] = []
    async with database._require_pool().acquire() as connection:
        if tag_keys:
            character_rows = await connection.fetch(
                """
                SELECT DISTINCT
                    c.id, c.name, c.category, c.universe, c.story_id,
                    EXISTS (
                        SELECT 1 FROM character_story_links AS csl
                        WHERE csl.character_id = c.id
                    ) AS has_multi_story,
                    a.normalized_alias
                FROM character_aliases AS a
                JOIN characters AS c ON c.id = a.character_id
                WHERE a.normalized_alias = ANY($1::TEXT[])
                """,
                tag_keys,
            )
            resolved_keys = {str(row["normalized_alias"]) for row in character_rows}
            unresolved = [
                display
                for display, normalized in hashtags
                if compact_identity(normalized) not in resolved_keys
                and not re.fullmatch(r"[a-f0-9]{6}", normalized)
            ]

        duplicate_draft = await connection.fetchrow(
            """
            SELECT id, status, published_at
            FROM publication_drafts
            WHERE target_chat_id = $1
              AND content_hash = $2
              AND id <> $3
              AND status IN ('scheduled', 'publishing', 'published')
            ORDER BY id DESC LIMIT 1
            """,
            draft.target_chat_id,
            draft.content_hash,
            draft.id,
        )
        duplicate_post = None
        if text:
            duplicate_post = await connection.fetchrow(
                """
                SELECT message_id, message_url, posted_at
                FROM channel_posts
                WHERE channel_id = $1
                  AND text_content = $2
                ORDER BY posted_at DESC LIMIT 1
                """,
                draft.target_chat_id,
                text,
            )

    if unresolved:
        issues.append(
            PublicationIssue(
                "unresolved_tags",
                "warning",
                "Нераспознанные хэштеги",
                ", ".join(f"#{value}" for value in unresolved[:12]),
            )
        )
    if classification.post_type in {"art", "prompt"} and not character_rows:
        issues.append(
            PublicationIssue(
                "no_character",
                "warning",
                "Не найден персонаж",
                "В посте нет хэштега, связанного с карточкой персонажа.",
            )
        )

    missing_category: list[str] = []
    missing_universe: list[str] = []
    missing_story: list[str] = []
    seen_characters: set[int] = set()
    for row in character_rows:
        character_id = int(row["id"])
        if character_id in seen_characters:
            continue
        seen_characters.add(character_id)
        name = str(row["name"])
        if not row["category"]:
            missing_category.append(name)
        if not row["universe"]:
            missing_universe.append(name)
        elif str(row["universe"]) in _STORY_REQUIRED_UNIVERSES:
            if row["story_id"] is None and not bool(row["has_multi_story"]):
                missing_story.append(name)
    if missing_category:
        issues.append(PublicationIssue("category", "error", "Нет категории", ", ".join(missing_category)))
    if missing_universe:
        issues.append(PublicationIssue("universe", "error", "Нет вселенной", ", ".join(missing_universe)))
    if missing_story:
        issues.append(PublicationIssue("story", "error", "Нет истории", ", ".join(missing_story)))

    if classification.post_type == "prompt":
        if not prompt.has_important:
            issues.append(PublicationIssue("prompt_important", "warning", "Нет блока ВАЖНО", "Структура промта неполная."))
        if not prompt.has_strict:
            issues.append(PublicationIssue("prompt_strict", "warning", "Нет блока СТРОГО", "Структура промта неполная."))
        if not prompt.has_technical:
            issues.append(PublicationIssue("prompt_technical", "warning", "Нет технического блока", "Не найдены камера, формат или параметры света."))

    if _ADULT_RE.search(text) and draft.items and not draft.has_spoiler:
        issues.append(
            PublicationIssue(
                "adult_spoiler",
                "warning",
                "Возможный 18+ без блюра",
                "Проверьте пост и включите спойлер перед публикацией.",
            )
        )

    links = extract_links(text)
    raw_candidates = _URL_CANDIDATE_RE.findall(text)
    if raw_candidates and not links:
        issues.append(PublicationIssue("links", "warning", "Проверьте ссылки", "Найдена ссылка, которую бот не смог разобрать."))

    if duplicate_draft is not None:
        issues.append(
            PublicationIssue(
                "duplicate_draft",
                "warning",
                "Похожий черновик уже используется",
                f"Черновик №{duplicate_draft['id']} имеет статус {duplicate_draft['status']}.",
            )
        )
    if duplicate_post is not None:
        detail = str(duplicate_post["message_url"] or f"message_id={duplicate_post['message_id']}")
        issues.append(PublicationIssue("duplicate_post", "warning", "Такой текст уже публиковался", detail))

    error_count = sum(issue.severity == "error" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)
    validation_status = "failed" if error_count else ("warning" if warning_count else "passed")
    status = draft.status
    if status in {"draft", "checked", "error"}:
        status = "checked"

    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                UPDATE publication_drafts
                SET status = $2,
                    post_type = $3,
                    validation_status = $4,
                    validation_error_count = $5,
                    validation_warning_count = $6,
                    validation_report = $7::JSONB,
                    last_error = CASE WHEN status = 'error' THEN NULL ELSE last_error END,
                    updated_at = NOW()
                WHERE id = $1 AND owner_id = $8
                """,
                draft.id,
                status,
                classification.post_type,
                validation_status,
                error_count,
                warning_count,
                json.dumps([issue.as_dict() for issue in issues], ensure_ascii=False),
                owner_id,
            )
            await _log_event(
                connection,
                draft.id,
                "validated",
                owner_id,
                {
                    "status": validation_status,
                    "errors": error_count,
                    "warnings": warning_count,
                },
            )
    result = await get_publication_draft(database, draft.id, owner_id=owner_id)
    if result is None:
        raise RuntimeError("Черновик исчез после проверки.")
    return result


async def set_publication_spoiler(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
    enabled: bool,
) -> PublicationDraft:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            result = await connection.execute(
                """
                UPDATE publication_drafts
                SET has_spoiler = $3, updated_at = NOW()
                WHERE id = $1 AND owner_id = $2
                """,
                draft_id,
                owner_id,
                enabled,
            )
            if result == "UPDATE 0":
                raise ValueError("Черновик не найден.")
            await connection.execute(
                "UPDATE publication_draft_items SET has_spoiler = $2 WHERE draft_id = $1",
                draft_id,
                enabled,
            )
            await _log_event(connection, draft_id, "spoiler_changed", owner_id, {"enabled": enabled})
    return await validate_publication_draft(database, draft_id, owner_id=owner_id)


async def update_publication_text(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
    text: str,
) -> PublicationDraft:
    cleaned = text.strip()
    draft = await get_publication_draft(database, draft_id, owner_id=owner_id)
    if draft is None:
        raise ValueError("Черновик не найден.")
    digest = _content_hash(
        cleaned,
        [item.telegram_file_unique_id or item.telegram_file_id for item in draft.items],
    )
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                UPDATE publication_drafts
                SET text_content = $3, content_hash = $4,
                    validation_status = 'pending', status = 'draft',
                    updated_at = NOW()
                WHERE id = $1 AND owner_id = $2
                """,
                draft_id,
                owner_id,
                cleaned,
                digest,
            )
            await _log_event(connection, draft_id, "text_changed", owner_id, {"length": len(cleaned)})
    return await validate_publication_draft(database, draft_id, owner_id=owner_id)


async def schedule_publication(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
    scheduled_at: datetime,
) -> PublicationDraft:
    draft = await validate_publication_draft(database, draft_id, owner_id=owner_id)
    if draft.validation_error_count:
        raise ValueError("Сначала исправьте ошибки проверки.")
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                UPDATE publication_drafts
                SET status = 'scheduled', scheduled_at = $3,
                    last_error = NULL, updated_at = NOW()
                WHERE id = $1 AND owner_id = $2
                """,
                draft_id,
                owner_id,
                scheduled_at,
            )
            await _log_event(connection, draft_id, "scheduled", owner_id, {"scheduled_at": scheduled_at.isoformat()})
    result = await get_publication_draft(database, draft_id, owner_id=owner_id)
    if result is None:
        raise RuntimeError("Запланированный черновик не найден.")
    return result


async def cancel_publication(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
) -> PublicationDraft:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            result = await connection.execute(
                """
                UPDATE publication_drafts
                SET status = 'cancelled', scheduled_at = NULL, updated_at = NOW()
                WHERE id = $1 AND owner_id = $2
                  AND status <> 'published'
                """,
                draft_id,
                owner_id,
            )
            if result == "UPDATE 0":
                raise ValueError("Черновик не найден или уже опубликован.")
            await _log_event(connection, draft_id, "cancelled", owner_id, {})
    result = await get_publication_draft(database, draft_id, owner_id=owner_id)
    if result is None:
        raise RuntimeError("Отменённый черновик не найден.")
    return result


async def retry_publication(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
) -> PublicationDraft:
    async with database._require_pool().acquire() as connection:
        result = await connection.execute(
            """
            UPDATE publication_drafts
            SET status = 'checked', last_error = NULL, updated_at = NOW()
            WHERE id = $1 AND owner_id = $2 AND status = 'error'
            """,
            draft_id,
            owner_id,
        )
        if result == "UPDATE 0":
            raise ValueError("Ошибка публикации не найдена.")
    return await validate_publication_draft(database, draft_id, owner_id=owner_id)
