from __future__ import annotations

import re
from dataclasses import dataclass

from velvet_bot.database import Character, Database

CATEGORY_ORDER = ("female", "male", "mf", "mm", "ff")
CATEGORY_LABELS = {
    "female": "Женский",
    "male": "Мужской",
    "mf": "МЖ",
    "mm": "ММ",
    "ff": "ЖЖ",
    "uncategorized": "Без категории",
}
CATEGORY_EMOJI = {
    "female": "👩",
    "male": "👨",
    "mf": "👩‍❤️‍👨",
    "mm": "👨‍❤️‍👨",
    "ff": "👩‍❤️‍👩",
    "uncategorized": "📦",
}
_CATEGORY_ALIASES = {
    "женский": "female",
    "женская": "female",
    "женщина": "female",
    "ж": "female",
    "female": "female",
    "мужской": "male",
    "мужчина": "male",
    "м": "male",
    "male": "male",
    "мж": "mf",
    "жм": "mf",
    "mf": "mf",
    "fm": "mf",
    "мм": "mm",
    "mm": "mm",
    "жж": "ff",
    "ff": "ff",
    "без": "uncategorized",
    "нет": "uncategorized",
    "none": "uncategorized",
    "uncategorized": "uncategorized",
}
_PROMPT_URL_RE = re.compile(
    r"^https://t\.me/(?:c/\d+|[A-Za-z0-9_]+)/\d+(?:\?[^\s]+)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CategorySummary:
    key: str
    label: str
    emoji: str
    character_count: int


@dataclass(frozen=True, slots=True)
class CharacterDirectoryItem:
    character: Character
    category: str | None
    prompt_post_url: str | None
    media_count: int


@dataclass(frozen=True, slots=True)
class CharacterDirectoryPage:
    items: list[CharacterDirectoryItem]
    category: str
    page: int
    page_size: int
    total_characters: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_characters + self.page_size - 1) // self.page_size)


def normalize_category(value: str, *, allow_uncategorized: bool = False) -> str:
    normalized = "".join(value.casefold().split())
    category = _CATEGORY_ALIASES.get(normalized)
    if category is None or (category == "uncategorized" and not allow_uncategorized):
        allowed = "женский, мужской, мж, мм, жж"
        raise ValueError(f"Неизвестная категория. Доступны: {allowed}.")
    return category


def category_label(category: str | None) -> str:
    return CATEGORY_LABELS.get(category or "uncategorized", CATEGORY_LABELS["uncategorized"])


def validate_prompt_post_url(value: str) -> str:
    cleaned = value.strip()
    if not _PROMPT_URL_RE.fullmatch(cleaned):
        raise ValueError(
            "Нужна ссылка на пост Telegram: https://t.me/channel/123 "
            "или https://t.me/c/1234567890/123."
        )
    return cleaned


def _row_to_character(row) -> Character:
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


async def set_character_category(
    database: Database,
    *,
    character_id: int,
    category: str | None,
) -> None:
    async with database._require_pool().acquire() as connection:
        result = await connection.execute(
            "UPDATE characters SET category = $2 WHERE id = $1",
            character_id,
            category,
        )
    if result.endswith("0"):
        raise ValueError("Персонаж не найден.")


async def set_character_prompt_url(
    database: Database,
    *,
    character_id: int,
    prompt_post_url: str | None,
) -> None:
    async with database._require_pool().acquire() as connection:
        result = await connection.execute(
            "UPDATE characters SET prompt_post_url = $2 WHERE id = $1",
            character_id,
            prompt_post_url,
        )
    if result.endswith("0"):
        raise ValueError("Персонаж не найден.")


async def get_character_directory_item(
    database: Database,
    character_id: int,
) -> CharacterDirectoryItem | None:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                c.id, c.name, c.created_by, c.created_in_chat, c.created_at,
                c.archive_chat_id, c.archive_thread_id, c.archive_topic_url,
                c.category, c.prompt_post_url,
                COUNT(cm.media_id) AS media_count
            FROM characters AS c
            LEFT JOIN character_media AS cm ON cm.character_id = c.id
            WHERE c.id = $1
            GROUP BY c.id
            """,
            character_id,
        )
    if row is None:
        return None
    return CharacterDirectoryItem(
        character=_row_to_character(row),
        category=row["category"],
        prompt_post_url=row["prompt_post_url"],
        media_count=int(row["media_count"] or 0),
    )


async def list_category_summaries(
    database: Database,
    *,
    public_only: bool,
    include_uncategorized: bool = False,
) -> list[CategorySummary]:
    keys = list(CATEGORY_ORDER)
    if include_uncategorized:
        keys.append("uncategorized")

    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                COALESCE(c.category, 'uncategorized') AS category,
                COUNT(DISTINCT c.id) AS character_count
            FROM characters AS c
            LEFT JOIN character_media AS cm ON cm.character_id = c.id
            WHERE ($1::BOOLEAN = FALSE OR cm.media_id IS NOT NULL)
            GROUP BY COALESCE(c.category, 'uncategorized')
            """,
            public_only,
        )
    counts = {str(row["category"]): int(row["character_count"] or 0) for row in rows}
    return [
        CategorySummary(
            key=key,
            label=CATEGORY_LABELS[key],
            emoji=CATEGORY_EMOJI[key],
            character_count=counts.get(key, 0),
        )
        for key in keys
    ]


async def list_character_directory(
    database: Database,
    *,
    category: str,
    page: int = 0,
    page_size: int = 6,
    public_only: bool,
) -> CharacterDirectoryPage:
    safe_page_size = max(1, min(page_size, 10))
    safe_page = max(0, page)
    category_value = None if category == "uncategorized" else category
    condition = "c.category IS NULL" if category == "uncategorized" else "c.category = $1"

    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT c.id
                    FROM characters AS c
                    LEFT JOIN character_media AS cm ON cm.character_id = c.id
                    WHERE {condition}
                      AND ($2::BOOLEAN = FALSE OR cm.media_id IS NOT NULL)
                    GROUP BY c.id
                ) AS directory
                """,
                category_value,
                public_only,
            )
            or 0
        )
        total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            f"""
            SELECT
                c.id, c.name, c.created_by, c.created_in_chat, c.created_at,
                c.archive_chat_id, c.archive_thread_id, c.archive_topic_url,
                c.category, c.prompt_post_url,
                COUNT(cm.media_id) AS media_count
            FROM characters AS c
            LEFT JOIN character_media AS cm ON cm.character_id = c.id
            WHERE {condition}
              AND ($2::BOOLEAN = FALSE OR cm.media_id IS NOT NULL)
            GROUP BY c.id
            ORDER BY c.normalized_name ASC, c.id ASC
            OFFSET $3
            LIMIT $4
            """,
            category_value,
            public_only,
            normalized_page * safe_page_size,
            safe_page_size,
        )

    items = [
        CharacterDirectoryItem(
            character=_row_to_character(row),
            category=row["category"],
            prompt_post_url=row["prompt_post_url"],
            media_count=int(row["media_count"] or 0),
        )
        for row in rows
    ]
    return CharacterDirectoryPage(
        items=items,
        category=category,
        page=normalized_page,
        page_size=safe_page_size,
        total_characters=total,
    )
