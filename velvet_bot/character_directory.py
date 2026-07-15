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

UNIVERSE_ORDER = ("shs", "kr", "lm", "lagerta", "original")
UNIVERSE_LABELS = {
    "shs": "SHS",
    "kr": "КР",
    "lm": "ЛМ",
    "lagerta": "Лагерта",
    "original": "Original",
    "uncategorized": "Без вселенной",
}
UNIVERSE_EMOJI = {
    "shs": "🔹",
    "kr": "💎",
    "lm": "🌙",
    "lagerta": "🛡",
    "original": "✦",
    "uncategorized": "📭",
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
_UNIVERSE_ALIASES = {
    "shs": "shs",
    "схс": "shs",
    "кр": "kr",
    "kr": "kr",
    "лм": "lm",
    "lm": "lm",
    "лагерта": "lagerta",
    "lagerta": "lagerta",
    "original": "original",
    "оригинал": "original",
    "ориг": "original",
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
    universe_category: str | None = None


@dataclass(frozen=True, slots=True)
class CharacterDirectoryPage:
    items: list[CharacterDirectoryItem]
    category: str
    page: int
    page_size: int
    total_characters: int
    universe_category: str = ""

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


def normalize_universe_category(
    value: str,
    *,
    allow_uncategorized: bool = False,
) -> str:
    normalized = "".join(value.casefold().split())
    universe = _UNIVERSE_ALIASES.get(normalized)
    if universe is None or (universe == "uncategorized" and not allow_uncategorized):
        allowed = "SHS, КР, ЛМ, Лагерта, Original"
        raise ValueError(f"Неизвестная вселенная. Доступны: {allowed}.")
    return universe


def category_label(category: str | None) -> str:
    return CATEGORY_LABELS.get(
        category or "uncategorized",
        CATEGORY_LABELS["uncategorized"],
    )


def universe_label(universe_category: str | None) -> str:
    return UNIVERSE_LABELS.get(
        universe_category or "uncategorized",
        UNIVERSE_LABELS["uncategorized"],
    )


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
    if result == "UPDATE 0":
        raise ValueError("Персонаж не найден.")


async def set_character_universe_category(
    database: Database,
    *,
    character_id: int,
    universe_category: str | None,
) -> None:
    async with database._require_pool().acquire() as connection:
        result = await connection.execute(
            "UPDATE characters SET universe_category = $2 WHERE id = $1",
            character_id,
            universe_category,
        )
    if result == "UPDATE 0":
        raise ValueError("Персонаж не найден.")


async def set_character_prompt_url(
    database: Database,
    *,
    character_id: int,
    prompt_post_url: str | None,
) -> None:
    """Legacy helper retained for migration compatibility."""
    async with database._require_pool().acquire() as connection:
        result = await connection.execute(
            "UPDATE characters SET prompt_post_url = $2 WHERE id = $1",
            character_id,
            prompt_post_url,
        )
    if result == "UPDATE 0":
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
                c.category, c.universe_category, c.prompt_post_url,
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
        universe_category=row["universe_category"],
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
            WHERE ($1::BOOLEAN = FALSE OR (cm.media_id IS NOT NULL AND c.category IS NOT NULL))
            GROUP BY COALESCE(c.category, 'uncategorized')
            """,
            public_only,
        )
    counts = {
        str(row["category"]): int(row["character_count"] or 0)
        for row in rows
    }
    return [
        CategorySummary(
            key=key,
            label=CATEGORY_LABELS[key],
            emoji=CATEGORY_EMOJI[key],
            character_count=counts.get(key, 0),
        )
        for key in keys
    ]


async def list_universe_summaries(
    database: Database,
    *,
    public_only: bool,
    include_uncategorized: bool = False,
) -> list[CategorySummary]:
    keys = list(UNIVERSE_ORDER)
    if include_uncategorized:
        keys.append("uncategorized")

    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                COALESCE(c.universe_category, 'uncategorized') AS universe_category,
                COUNT(DISTINCT c.id) AS character_count
            FROM characters AS c
            LEFT JOIN character_media AS cm ON cm.character_id = c.id
            WHERE ($1::BOOLEAN = FALSE OR (cm.media_id IS NOT NULL AND c.category IS NOT NULL))
            GROUP BY COALESCE(c.universe_category, 'uncategorized')
            """,
            public_only,
        )
    counts = {
        str(row["universe_category"]): int(row["character_count"] or 0)
        for row in rows
    }
    return [
        CategorySummary(
            key=key,
            label=UNIVERSE_LABELS[key],
            emoji=UNIVERSE_EMOJI[key],
            character_count=counts.get(key, 0),
        )
        for key in keys
    ]


async def list_character_directory(
    database: Database,
    *,
    category: str = "",
    universe_category: str = "",
    page: int = 0,
    page_size: int = 6,
    public_only: bool,
) -> CharacterDirectoryPage:
    category_filter = "" if category in {"", "all"} else category
    universe_filter = "" if universe_category in {"", "all"} else universe_category
    if category_filter not in {*CATEGORY_ORDER, "uncategorized", ""}:
        raise ValueError("Неизвестная категория архива.")
    if universe_filter not in {*UNIVERSE_ORDER, "uncategorized", ""}:
        raise ValueError("Неизвестная вселенная архива.")

    safe_page_size = max(1, min(page_size, 10))
    safe_page = max(0, page)
    category_condition = """
        ($1::TEXT = '' OR
         ($1::TEXT = 'uncategorized' AND c.category IS NULL) OR
         c.category = $1)
    """
    universe_condition = """
        ($2::TEXT = '' OR
         ($2::TEXT = 'uncategorized' AND c.universe_category IS NULL) OR
         c.universe_category = $2)
    """
    public_condition = """
        ($3::BOOLEAN = FALSE OR (cm.media_id IS NOT NULL AND c.category IS NOT NULL))
    """

    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT c.id
                    FROM characters AS c
                    LEFT JOIN character_media AS cm ON cm.character_id = c.id
                    WHERE {category_condition}
                      AND {universe_condition}
                      AND {public_condition}
                    GROUP BY c.id
                ) AS directory
                """,
                category_filter,
                universe_filter,
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
                c.category, c.universe_category, c.prompt_post_url,
                COUNT(cm.media_id) AS media_count
            FROM characters AS c
            LEFT JOIN character_media AS cm ON cm.character_id = c.id
            WHERE {category_condition}
              AND {universe_condition}
              AND {public_condition}
            GROUP BY c.id
            ORDER BY c.normalized_name ASC, c.id ASC
            OFFSET $4
            LIMIT $5
            """,
            category_filter,
            universe_filter,
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
            universe_category=row["universe_category"],
        )
        for row in rows
    ]
    return CharacterDirectoryPage(
        items=items,
        category=category_filter,
        page=normalized_page,
        page_size=safe_page_size,
        total_characters=total,
        universe_category=universe_filter,
    )
