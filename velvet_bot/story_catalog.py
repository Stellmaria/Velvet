from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from velvet_bot.database import Database

STORY_REQUIRED_UNIVERSES = frozenset({"shs", "kr", "lm", "idm"})
KNOWN_UNIVERSES = frozenset(
    {"shs", "kr", "lm", "idm", "bg3", "lagerta", "original"}
)
_STORY_KEY_RE = re.compile(r"[^\w]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class CharacterStory:
    id: int
    universe: str
    key: str
    short_label: str
    title: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class StorySummary:
    id: int
    universe: str
    key: str
    short_label: str
    title: str
    character_count: int


def universe_requires_story(universe: str | None) -> bool:
    return bool(universe and universe in STORY_REQUIRED_UNIVERSES)


def clean_story_short_label(value: str) -> str:
    cleaned = "".join(unicodedata.normalize("NFKC", value).upper().split())
    if not cleaned:
        raise ValueError("Сокращение истории не может быть пустым.")
    if len(cleaned) > 16:
        raise ValueError("Сокращение истории не должно быть длиннее 16 символов.")
    return cleaned


def clean_story_title(value: str) -> str:
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    if not cleaned:
        raise ValueError("Название истории не может быть пустым.")
    if len(cleaned) > 160:
        raise ValueError("Название истории не должно быть длиннее 160 символов.")
    return cleaned


def make_story_key(short_label: str) -> str:
    normalized = unicodedata.normalize("NFKC", short_label).casefold()
    key = _STORY_KEY_RE.sub("_", normalized).strip("_")
    if not key:
        raise ValueError("Не удалось сформировать ключ истории.")
    return key[:64]


def _row_to_story(row) -> CharacterStory:
    return CharacterStory(
        id=int(row["id"]),
        universe=str(row["universe"]),
        key=str(row["key"]),
        short_label=str(row["short_label"]),
        title=str(row["title"]),
        sort_order=int(row["sort_order"] or 0),
    )


async def get_story(database: Database, story_id: int) -> CharacterStory | None:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id, universe, key, short_label, title, sort_order
            FROM character_stories
            WHERE id = $1
            """,
            story_id,
        )
    return _row_to_story(row) if row is not None else None


async def list_stories(
    database: Database,
    *,
    universe: str,
) -> list[CharacterStory]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id, universe, key, short_label, title, sort_order
            FROM character_stories
            WHERE universe = $1
            ORDER BY sort_order, title, id
            """,
            universe,
        )
    return [_row_to_story(row) for row in rows]


async def find_story(
    database: Database,
    *,
    universe: str,
    value: str,
) -> CharacterStory | None:
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id, universe, key, short_label, title, sort_order
            FROM character_stories
            WHERE universe = $1
              AND (
                    LOWER(short_label) = LOWER($2)
                    OR LOWER(key) = LOWER($2)
                    OR LOWER(title) = LOWER($2)
                  )
            ORDER BY sort_order, id
            LIMIT 1
            """,
            universe,
            cleaned,
        )
    return _row_to_story(row) if row is not None else None


async def create_story(
    database: Database,
    *,
    universe: str,
    short_label: str,
    title: str,
) -> CharacterStory:
    if universe not in KNOWN_UNIVERSES:
        raise ValueError("Неизвестная вселенная.")
    cleaned_short = clean_story_short_label(short_label)
    cleaned_title = clean_story_title(title)
    key = make_story_key(cleaned_short)

    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            INSERT INTO character_stories (
                universe,
                key,
                short_label,
                title,
                sort_order
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                COALESCE(
                    (
                        SELECT MAX(sort_order) + 10
                        FROM character_stories
                        WHERE universe = $1
                    ),
                    10
                )
            )
            ON CONFLICT (universe, key) DO UPDATE
            SET short_label = EXCLUDED.short_label,
                title = EXCLUDED.title
            RETURNING id, universe, key, short_label, title, sort_order
            """,
            universe,
            key,
            cleaned_short,
            cleaned_title,
        )
    if row is None:
        raise RuntimeError("Не удалось сохранить историю.")
    return _row_to_story(row)


async def set_character_story(
    database: Database,
    *,
    character_id: int,
    story_id: int | None,
) -> None:
    async with database._require_pool().acquire() as connection:
        if story_id is None:
            result = await connection.execute(
                "UPDATE characters SET story_id = NULL WHERE id = $1",
                character_id,
            )
        else:
            result = await connection.execute(
                """
                UPDATE characters AS c
                SET story_id = s.id
                FROM character_stories AS s
                WHERE c.id = $1
                  AND s.id = $2
                  AND c.universe = s.universe
                """,
                character_id,
                story_id,
            )
    if result == "UPDATE 0":
        raise ValueError(
            "Персонаж не найден или история относится к другой вселенной."
        )


async def list_story_summaries(
    database: Database,
    *,
    category: str,
    universe: str,
    public_only: bool,
) -> list[StorySummary]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                s.id,
                s.universe,
                s.key,
                s.short_label,
                s.title,
                s.sort_order,
                COUNT(DISTINCT c.id) FILTER (
                    WHERE c.category = $1
                      AND c.universe = $2
                      AND (
                            $3::BOOLEAN = FALSE
                            OR cm.media_id IS NOT NULL
                          )
                ) AS character_count
            FROM character_stories AS s
            LEFT JOIN characters AS c ON c.story_id = s.id
            LEFT JOIN character_media AS cm ON cm.character_id = c.id
            WHERE s.universe = $2
            GROUP BY s.id
            ORDER BY s.sort_order, s.title, s.id
            """,
            category,
            universe,
            public_only,
        )

    summaries = [
        StorySummary(
            id=int(row["id"]),
            universe=str(row["universe"]),
            key=str(row["key"]),
            short_label=str(row["short_label"]),
            title=str(row["title"]),
            character_count=int(row["character_count"] or 0),
        )
        for row in rows
    ]
    if public_only:
        return [item for item in summaries if item.character_count > 0]
    return summaries
