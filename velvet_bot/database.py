from __future__ import annotations

import unicodedata
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import aiosqlite


MAX_CHARACTER_NAME_LENGTH = 64


@dataclass(frozen=True, slots=True)
class Character:
    id: int
    name: str
    created_by: int | None
    created_in_chat: int | None
    created_at: str


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


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        async with self._connect() as connection:
            await connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    created_by INTEGER,
                    created_in_chat INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS media_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_file_id TEXT NOT NULL,
                    telegram_file_unique_id TEXT NOT NULL UNIQUE,
                    original_file_name TEXT,
                    storage_file_name TEXT NOT NULL UNIQUE,
                    media_type TEXT NOT NULL,
                    file_size INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS character_media (
                    character_id INTEGER NOT NULL,
                    media_id INTEGER NOT NULL,
                    saved_by INTEGER,
                    saved_in_chat INTEGER,
                    source_message_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (character_id, media_id),
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
                    FOREIGN KEY (media_id) REFERENCES media_files(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_character_media_character
                    ON character_media(character_id);
                """
            )
            await connection.commit()

    async def create_character(
        self,
        name: str,
        *,
        created_by: int | None,
        created_in_chat: int | None,
    ) -> tuple[Character, bool]:
        display_name = clean_character_name(name)
        normalized_name = normalize_character_name(display_name)

        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                INSERT OR IGNORE INTO characters (
                    name,
                    normalized_name,
                    created_by,
                    created_in_chat
                )
                VALUES (?, ?, ?, ?)
                """,
                (display_name, normalized_name, created_by, created_in_chat),
            )
            await connection.commit()

            created = cursor.rowcount == 1
            row = await self._fetch_character_row(
                connection,
                normalized_name=normalized_name,
            )

        if row is None:
            raise RuntimeError("Не удалось создать или получить профиль персонажа.")

        return self._row_to_character(row), created

    async def get_character(self, name: str) -> Character | None:
        normalized_name = normalize_character_name(name)

        async with self._connect() as connection:
            row = await self._fetch_character_row(
                connection,
                normalized_name=normalized_name,
            )

        return self._row_to_character(row) if row is not None else None

    async def list_characters(self, *, limit: int = 100) -> list[Character]:
        safe_limit = max(1, min(limit, 100))

        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT id, name, created_by, created_in_chat, created_at
                FROM characters
                ORDER BY normalized_name
                LIMIT ?
                """,
                (safe_limit,),
            )
            rows = await cursor.fetchall()

        return [self._row_to_character(row) for row in rows]

    async def count_character_media(self, character_id: int) -> int:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT COUNT(*) AS media_count
                FROM character_media
                WHERE character_id = ?
                """,
                (character_id,),
            )
            row = await cursor.fetchone()

        return int(row["media_count"]) if row is not None else 0

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.path) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys = ON")
            yield connection

    @staticmethod
    async def _fetch_character_row(
        connection: aiosqlite.Connection,
        *,
        normalized_name: str,
    ) -> aiosqlite.Row | None:
        cursor = await connection.execute(
            """
            SELECT id, name, created_by, created_in_chat, created_at
            FROM characters
            WHERE normalized_name = ?
            """,
            (normalized_name,),
        )
        return await cursor.fetchone()

    @staticmethod
    def _row_to_character(row: aiosqlite.Row) -> Character:
        return Character(
            id=int(row["id"]),
            name=str(row["name"]),
            created_by=row["created_by"],
            created_in_chat=row["created_in_chat"],
            created_at=str(row["created_at"]),
        )
