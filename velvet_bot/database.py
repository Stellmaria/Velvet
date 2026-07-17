from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import asyncpg

from velvet_bot.media import MediaDescriptor

MAX_CHARACTER_NAME_LENGTH = 64
_LEGACY_DUPLICATE_MIGRATION_NUMBERS = {
    "003": frozenset({"003_character_references.sql", "003_public_archive.sql"}),
}


@dataclass(frozen=True, slots=True)
class Character:
    id: int
    name: str
    created_by: int | None
    created_in_chat: int | None
    created_at: datetime
    archive_chat_id: int | None
    archive_thread_id: int | None
    archive_topic_url: str | None


@dataclass(frozen=True, slots=True)
class SaveMediaResult:
    character: Character
    media_id: int
    media_created: bool
    character_link_created: bool
    storage_file_name: str
    archive_message_id: int | None


def clean_character_name(value: str) -> str:
    """Normalize whitespace while preserving the character's display name."""
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    if not cleaned:
        raise ValueError("Имя персонажа не может быть пустым.")
    if len(cleaned) > MAX_CHARACTER_NAME_LENGTH:
        raise ValueError(
            f"Имя персонажа не должно быть длиннее {MAX_CHARACTER_NAME_LENGTH} символов."
        )
    return cleaned


def normalize_character_name(value: str) -> str:
    """Return a case-insensitive key used to prevent duplicate profiles."""
    return clean_character_name(value).casefold()


def _migration_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_migration_catalog(migration_files: list[Path]) -> None:
    """Reject ambiguous new migration numbers while preserving the legacy 003 pair."""
    by_number: dict[str, set[str]] = {}
    for path in migration_files:
        number, separator, _ = path.name.partition("_")
        if not separator or not number.isdigit():
            continue
        by_number.setdefault(number, set()).add(path.name)

    for number, names in sorted(by_number.items()):
        if len(names) <= 1:
            continue
        allowed = _LEGACY_DUPLICATE_MIGRATION_NUMBERS.get(number)
        if allowed == frozenset(names):
            continue
        joined = ", ".join(sorted(names))
        raise RuntimeError(
            f"Номер миграции {number} используется несколькими файлами: {joined}. "
            "Создайте следующий свободный номер; переименование уже применённой "
            "миграции запрещено."
        )


class Database:
    def __init__(self, database_url: str, *, migrations_path: Path | None = None) -> None:
        self.database_url = database_url
        self.migrations_path = (
            migrations_path
            or Path(__file__).resolve().parents[1] / "migrations"
        )
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        self._pool = await asyncpg.create_pool(
            dsn=self.database_url,
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
        try:
            await self._apply_migrations()
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def create_character(
        self,
        name: str,
        *,
        created_by: int | None,
        created_in_chat: int | None,
    ) -> tuple[Character, bool]:
        display_name = clean_character_name(name)
        normalized_name = normalize_character_name(display_name)

        async with self._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO characters (
                    name,
                    normalized_name,
                    created_by,
                    created_in_chat
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (normalized_name) DO NOTHING
                RETURNING
                    id,
                    name,
                    created_by,
                    created_in_chat,
                    created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                """,
                display_name,
                normalized_name,
                created_by,
                created_in_chat,
            )
            created = row is not None
            if row is None:
                row = await self._fetch_character_row(
                    connection,
                    normalized_name=normalized_name,
                )

        if row is None:
            raise RuntimeError("Не удалось создать или получить профиль персонажа.")

        return self._row_to_character(row), created

    async def bind_character_topic(
        self,
        character_id: int,
        *,
        archive_chat_id: int,
        archive_thread_id: int,
        archive_topic_url: str,
    ) -> Character:
        try:
            async with self._require_pool().acquire() as connection:
                row = await connection.fetchrow(
                    """
                    UPDATE characters
                    SET archive_chat_id = $2,
                        archive_thread_id = $3,
                        archive_topic_url = $4
                    WHERE id = $1
                    RETURNING
                        id,
                        name,
                        created_by,
                        created_in_chat,
                        created_at,
                        archive_chat_id,
                        archive_thread_id,
                        archive_topic_url
                    """,
                    character_id,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url,
                )
        except asyncpg.UniqueViolationError as error:
            raise ValueError(
                "Эта тема Telegram уже привязана к другому персонажу."
            ) from error

        if row is None:
            raise RuntimeError("Персонаж для привязки темы не найден.")
        return self._row_to_character(row)

    async def get_character(self, name: str) -> Character | None:
        normalized_name = normalize_character_name(name)
        async with self._require_pool().acquire() as connection:
            row = await self._fetch_character_row(
                connection,
                normalized_name=normalized_name,
            )
        return self._row_to_character(row) if row is not None else None

    async def get_character_by_archive_topic(
        self,
        archive_chat_id: int,
        archive_thread_id: int,
    ) -> Character | None:
        async with self._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    id,
                    name,
                    created_by,
                    created_in_chat,
                    created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                FROM characters
                WHERE archive_chat_id = $1
                  AND archive_thread_id = $2
                """,
                archive_chat_id,
                archive_thread_id,
            )
        return self._row_to_character(row) if row is not None else None

    async def list_characters(self, *, limit: int = 100) -> list[Character]:
        safe_limit = max(1, min(limit, 100))
        async with self._require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    id,
                    name,
                    created_by,
                    created_in_chat,
                    created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                FROM characters
                ORDER BY normalized_name
                LIMIT $1
                """,
                safe_limit,
            )
        return [self._row_to_character(row) for row in rows]

    async def count_character_media(self, character_id: int) -> int:
        async with self._require_pool().acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM character_media
                WHERE character_id = $1
                """,
                character_id,
            )
        return int(value or 0)

    async def save_character_media(
        self,
        character: Character,
        media: MediaDescriptor,
        *,
        saved_by: int | None,
        saved_in_chat: int,
        source_chat_id: int,
        source_message_id: int,
        source_thread_id: int | None,
        command_message_id: int | None,
        archive_message_id: int | None = None,
    ) -> SaveMediaResult:
        async with self._require_pool().acquire() as connection:
            async with connection.transaction():
                media_row = await connection.fetchrow(
                    """
                    INSERT INTO media_files (
                        telegram_file_id,
                        telegram_file_unique_id,
                        original_file_name,
                        storage_file_name,
                        media_type,
                        mime_type,
                        file_size
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (telegram_file_unique_id) DO NOTHING
                    RETURNING id, storage_file_name
                    """,
                    media.telegram_file_id,
                    media.telegram_file_unique_id,
                    media.original_file_name,
                    media.storage_file_name,
                    media.media_type,
                    media.mime_type,
                    media.file_size,
                )
                media_created = media_row is not None

                if media_row is None:
                    media_row = await connection.fetchrow(
                        """
                        UPDATE media_files
                        SET telegram_file_id = $2,
                            original_file_name = COALESCE(original_file_name, $3),
                            mime_type = COALESCE(mime_type, $4),
                            file_size = COALESCE(file_size, $5)
                        WHERE telegram_file_unique_id = $1
                        RETURNING id, storage_file_name
                        """,
                        media.telegram_file_unique_id,
                        media.telegram_file_id,
                        media.original_file_name,
                        media.mime_type,
                        media.file_size,
                    )

                if media_row is None:
                    raise RuntimeError("Не удалось сохранить данные медиафайла.")

                link_row = await connection.fetchrow(
                    """
                    INSERT INTO character_media (
                        character_id,
                        media_id,
                        saved_by,
                        saved_in_chat,
                        source_chat_id,
                        source_message_id,
                        source_thread_id,
                        command_message_id,
                        archive_message_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (character_id, media_id) DO NOTHING
                    RETURNING archive_message_id
                    """,
                    character.id,
                    int(media_row["id"]),
                    saved_by,
                    saved_in_chat,
                    source_chat_id,
                    source_message_id,
                    source_thread_id,
                    command_message_id,
                    archive_message_id,
                )
                character_link_created = link_row is not None

                if link_row is None:
                    existing_archive_message_id = await connection.fetchval(
                        """
                        SELECT archive_message_id
                        FROM character_media
                        WHERE character_id = $1 AND media_id = $2
                        """,
                        character.id,
                        int(media_row["id"]),
                    )
                else:
                    existing_archive_message_id = link_row["archive_message_id"]

        return SaveMediaResult(
            character=character,
            media_id=int(media_row["id"]),
            media_created=media_created,
            character_link_created=character_link_created,
            storage_file_name=str(media_row["storage_file_name"]),
            archive_message_id=(
                int(existing_archive_message_id)
                if existing_archive_message_id is not None
                else None
            ),
        )

    async def set_archive_message_id(
        self,
        character_id: int,
        media_id: int,
        archive_message_id: int,
    ) -> int:
        async with self._require_pool().acquire() as connection:
            value = await connection.fetchval(
                """
                UPDATE character_media
                SET archive_message_id = COALESCE(archive_message_id, $3)
                WHERE character_id = $1 AND media_id = $2
                RETURNING archive_message_id
                """,
                character_id,
                media_id,
                archive_message_id,
            )
        if value is None:
            raise RuntimeError("Связь персонажа с медиафайлом не найдена.")
        return int(value)

    async def _apply_migrations(self) -> None:
        migration_files = sorted(self.migrations_path.glob("*.sql"))
        if not migration_files:
            raise RuntimeError(f"Не найдены SQL-миграции в {self.migrations_path}.")
        _validate_migration_catalog(migration_files)

        async with self._require_pool().acquire() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await connection.execute(
                "ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT"
            )

            for migration_file in migration_files:
                version = migration_file.name
                checksum = _migration_checksum(migration_file)
                applied = await connection.fetchrow(
                    "SELECT checksum FROM schema_migrations WHERE version = $1",
                    version,
                )
                if applied is not None:
                    stored_checksum = applied["checksum"]
                    if stored_checksum is None:
                        await connection.execute(
                            "UPDATE schema_migrations SET checksum = $2 WHERE version = $1",
                            version,
                            checksum,
                        )
                    elif str(stored_checksum) != checksum:
                        raise RuntimeError(
                            f"Применённая миграция {version} была изменена. "
                            "Верните исходный SQL и создайте новую миграцию."
                        )
                    continue

                sql = migration_file.read_text(encoding="utf-8")
                async with connection.transaction():
                    await connection.execute(sql)
                    await connection.execute(
                        "INSERT INTO schema_migrations (version, checksum) VALUES ($1, $2)",
                        version,
                        checksum,
                    )

    def acquire(self):
        """Return a public PostgreSQL connection acquisition context."""
        return self._require_pool().acquire()

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Подключение к PostgreSQL ещё не инициализировано.")
        return self._pool

    @staticmethod
    async def _fetch_character_row(
        connection: asyncpg.Connection,
        *,
        normalized_name: str,
    ) -> asyncpg.Record | None:
        return await connection.fetchrow(
            """
            SELECT
                id,
                name,
                created_by,
                created_in_chat,
                created_at,
                archive_chat_id,
                archive_thread_id,
                archive_topic_url
            FROM characters
            WHERE normalized_name = $1
            """,
            normalized_name,
        )

    @staticmethod
    def _row_to_character(row: asyncpg.Record) -> Character:
        return Character(
            id=int(row["id"]),
            name=str(row["name"]),
            created_by=row["created_by"],
            created_in_chat=row["created_in_chat"],
            created_at=row["created_at"],
            archive_chat_id=row["archive_chat_id"],
            archive_thread_id=row["archive_thread_id"],
            archive_topic_url=row["archive_topic_url"],
        )


__all__ = (
    "Character",
    "Database",
    "MAX_CHARACTER_NAME_LENGTH",
    "SaveMediaResult",
    "clean_character_name",
    "normalize_character_name",
)
