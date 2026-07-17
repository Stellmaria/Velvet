from __future__ import annotations

import json
from datetime import datetime

from velvet_bot.database import Database
from velvet_bot.domains.publication.models import (
    PublicationDraft,
    PublicationInboxItem,
    PublicationInboxPayload,
)
from velvet_bot.domains.publication.repository import PublicationRepository


class PublicationDraftRepository:
    """Persistence boundary for inbox capture and draft editing commands."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._drafts = PublicationRepository(database)

    async def capture_inbox(self, payload: PublicationInboxPayload) -> None:
        if payload.telegram_file_id is None and not payload.text_content:
            return
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO publication_inbox_items (
                    owner_id, source_chat_id, source_message_id, media_group_id,
                    text_content, telegram_file_id, telegram_file_unique_id,
                    media_type, mime_type, file_name, file_size, has_spoiler,
                    received_at
                )
                VALUES (
                    $1::BIGINT, $2::BIGINT, $3::BIGINT, $4::TEXT,
                    $5::TEXT, $6::TEXT, $7::TEXT,
                    $8::VARCHAR, $9::TEXT, $10::TEXT, $11::BIGINT, $12::BOOLEAN,
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
                payload.owner_id,
                payload.source_chat_id,
                payload.source_message_id,
                payload.media_group_id,
                payload.text_content,
                payload.telegram_file_id,
                payload.telegram_file_unique_id,
                payload.media_type,
                payload.mime_type,
                payload.file_name,
                payload.file_size,
                payload.has_spoiler,
            )

    async def list_source_items(
        self,
        payload: PublicationInboxPayload,
    ) -> tuple[PublicationInboxItem, ...]:
        async with self._database.acquire() as connection:
            if payload.media_group_id:
                rows = await connection.fetch(
                    """
                    SELECT *
                    FROM publication_inbox_items
                    WHERE owner_id = $1::BIGINT
                      AND source_chat_id = $2::BIGINT
                      AND media_group_id = $3::TEXT
                    ORDER BY source_message_id
                    """,
                    payload.owner_id,
                    payload.source_chat_id,
                    payload.media_group_id,
                )
            else:
                rows = await connection.fetch(
                    """
                    SELECT *
                    FROM publication_inbox_items
                    WHERE owner_id = $1::BIGINT
                      AND source_chat_id = $2::BIGINT
                      AND source_message_id = $3::BIGINT
                    """,
                    payload.owner_id,
                    payload.source_chat_id,
                    payload.source_message_id,
                )
        return tuple(self._row_to_inbox_item(row) for row in rows)

    async def create_draft(
        self,
        *,
        source: PublicationInboxPayload,
        target_chat_id: int,
        text_content: str,
        post_type: str,
        content_hash: str,
        has_spoiler: bool,
        items: tuple[PublicationInboxItem, ...],
    ) -> PublicationDraft:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                draft_id = await connection.fetchval(
                    """
                    INSERT INTO publication_drafts (
                        owner_id, target_chat_id, source_chat_id, source_message_id,
                        source_media_group_id, text_content, status, post_type,
                        has_spoiler, content_hash, updated_at
                    )
                    VALUES (
                        $1::BIGINT, $2::BIGINT, $3::BIGINT, $4::BIGINT,
                        $5::TEXT, $6::TEXT, 'draft', $7::VARCHAR,
                        $8::BOOLEAN, $9::CHAR(64), NOW()
                    )
                    RETURNING id
                    """,
                    source.owner_id,
                    int(target_chat_id),
                    source.source_chat_id,
                    source.source_message_id,
                    source.media_group_id,
                    text_content,
                    post_type,
                    has_spoiler,
                    content_hash,
                )
                if draft_id is None:
                    raise RuntimeError("Не удалось создать черновик.")

                position = 0
                for item in items:
                    payload = item.payload
                    if not payload.telegram_file_id:
                        continue
                    await connection.execute(
                        """
                        INSERT INTO publication_draft_items (
                            draft_id, position, telegram_file_id,
                            telegram_file_unique_id, media_type, mime_type,
                            file_name, file_size, source_message_id, has_spoiler
                        )
                        VALUES (
                            $1::BIGINT, $2::INTEGER, $3::TEXT,
                            $4::TEXT, $5::VARCHAR, $6::TEXT,
                            $7::TEXT, $8::BIGINT, $9::BIGINT, $10::BOOLEAN
                        )
                        """,
                        int(draft_id),
                        position,
                        payload.telegram_file_id,
                        payload.telegram_file_unique_id,
                        payload.media_type,
                        payload.mime_type,
                        payload.file_name,
                        payload.file_size,
                        payload.source_message_id,
                        payload.has_spoiler,
                    )
                    position += 1

                await self._log_event_on_connection(
                    connection,
                    draft_id=int(draft_id),
                    event_type="created",
                    actor_id=source.owner_id,
                    details={"source_message_id": source.source_message_id},
                )

        result = await self._drafts.get_draft(int(draft_id), owner_id=source.owner_id)
        if result is None:
            raise RuntimeError("Созданный черновик не найден.")
        return result

    async def set_spoiler(
        self,
        draft_id: int,
        *,
        owner_id: int,
        enabled: bool,
    ) -> None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET has_spoiler = $3::BOOLEAN, updated_at = NOW()
                    WHERE id = $1::BIGINT AND owner_id = $2::BIGINT
                    """,
                    int(draft_id),
                    int(owner_id),
                    bool(enabled),
                )
                if result == "UPDATE 0":
                    raise ValueError("Черновик не найден.")
                await connection.execute(
                    """
                    UPDATE publication_draft_items
                    SET has_spoiler = $2::BOOLEAN
                    WHERE draft_id = $1::BIGINT
                    """,
                    int(draft_id),
                    bool(enabled),
                )
                await self._log_event_on_connection(
                    connection,
                    draft_id=int(draft_id),
                    event_type="spoiler_changed",
                    actor_id=int(owner_id),
                    details={"enabled": bool(enabled)},
                )

    async def update_text(
        self,
        draft_id: int,
        *,
        owner_id: int,
        text: str,
        content_hash: str,
    ) -> None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET text_content = $3::TEXT,
                        content_hash = $4::CHAR(64),
                        validation_status = 'pending',
                        status = 'draft',
                        updated_at = NOW()
                    WHERE id = $1::BIGINT AND owner_id = $2::BIGINT
                    """,
                    int(draft_id),
                    int(owner_id),
                    text,
                    content_hash,
                )
                if result == "UPDATE 0":
                    raise ValueError("Черновик не найден.")
                await self._log_event_on_connection(
                    connection,
                    draft_id=int(draft_id),
                    event_type="text_changed",
                    actor_id=int(owner_id),
                    details={"length": len(text)},
                )

    async def schedule(
        self,
        draft_id: int,
        *,
        owner_id: int,
        scheduled_at: datetime,
    ) -> PublicationDraft:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = 'scheduled',
                        scheduled_at = $3::TIMESTAMPTZ,
                        last_error = NULL,
                        updated_at = NOW()
                    WHERE id = $1::BIGINT AND owner_id = $2::BIGINT
                    """,
                    int(draft_id),
                    int(owner_id),
                    scheduled_at,
                )
                if result == "UPDATE 0":
                    raise ValueError("Черновик не найден.")
                await self._log_event_on_connection(
                    connection,
                    draft_id=int(draft_id),
                    event_type="scheduled",
                    actor_id=int(owner_id),
                    details={"scheduled_at": scheduled_at.isoformat()},
                )
        return await self._require_draft(draft_id, owner_id=owner_id, missing="Запланированный черновик не найден.")

    async def cancel(self, draft_id: int, *, owner_id: int) -> PublicationDraft:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = 'cancelled',
                        scheduled_at = NULL,
                        updated_at = NOW()
                    WHERE id = $1::BIGINT
                      AND owner_id = $2::BIGINT
                      AND status <> 'published'
                    """,
                    int(draft_id),
                    int(owner_id),
                )
                if result == "UPDATE 0":
                    raise ValueError("Черновик не найден или уже опубликован.")
                await self._log_event_on_connection(
                    connection,
                    draft_id=int(draft_id),
                    event_type="cancelled",
                    actor_id=int(owner_id),
                    details={},
                )
        return await self._require_draft(draft_id, owner_id=owner_id, missing="Отменённый черновик не найден.")

    async def retry(self, draft_id: int, *, owner_id: int) -> None:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE publication_drafts
                SET status = 'checked', last_error = NULL, updated_at = NOW()
                WHERE id = $1::BIGINT
                  AND owner_id = $2::BIGINT
                  AND status = 'error'
                """,
                int(draft_id),
                int(owner_id),
            )
        if result == "UPDATE 0":
            raise ValueError("Ошибка публикации не найдена.")

    async def _require_draft(
        self,
        draft_id: int,
        *,
        owner_id: int,
        missing: str,
    ) -> PublicationDraft:
        result = await self._drafts.get_draft(draft_id, owner_id=owner_id)
        if result is None:
            raise RuntimeError(missing)
        return result

    @staticmethod
    async def _log_event_on_connection(
        connection,
        *,
        draft_id: int,
        event_type: str,
        actor_id: int | None,
        details: dict,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO publication_events (
                draft_id, event_type, actor_id, details
            )
            VALUES ($1::BIGINT, $2::VARCHAR, $3::BIGINT, $4::JSONB)
            """,
            draft_id,
            event_type,
            actor_id,
            json.dumps(details, ensure_ascii=False),
        )

    @staticmethod
    def _row_to_inbox_item(row) -> PublicationInboxItem:
        payload = PublicationInboxPayload(
            owner_id=int(row["owner_id"]),
            source_chat_id=int(row["source_chat_id"]),
            source_message_id=int(row["source_message_id"]),
            media_group_id=row["media_group_id"],
            text_content=str(row["text_content"] or ""),
            telegram_file_id=row["telegram_file_id"],
            telegram_file_unique_id=row["telegram_file_unique_id"],
            media_type=str(row["media_type"]),
            mime_type=row["mime_type"],
            file_name=row["file_name"],
            file_size=(int(row["file_size"]) if row["file_size"] is not None else None),
            has_spoiler=bool(row["has_spoiler"]),
        )
        return PublicationInboxItem(id=int(row["id"]), payload=payload)


__all__ = ("PublicationDraftRepository",)
