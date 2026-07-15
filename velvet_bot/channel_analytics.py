from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from aiogram.types import Message

from velvet_bot.database import Database

_HASHTAG_RE = re.compile(r"(?<![\w#])#([\w]+)", re.UNICODE)
_URL_RE = re.compile(
    r"(?:https?://[^\s<>\]\[()]+|(?<![\w.])t\.me/[A-Za-z0-9_+/=?&.-]+)",
    re.IGNORECASE,
)
_HEX_RE = re.compile(r"(?<![A-Fa-f0-9])#[A-Fa-f0-9]{6}(?![A-Fa-f0-9])")


@dataclass(frozen=True, slots=True)
class PromptSignals:
    is_prompt: bool
    score: int
    has_important: bool
    has_strict: bool
    has_negative: bool
    has_technical: bool
    has_palette: bool


@dataclass(frozen=True, slots=True)
class ParsedChannelPost:
    channel_id: int
    message_id: int
    publication_key: str
    posted_at: datetime
    edited_at: datetime | None
    title: str | None
    username: str | None
    author_signature: str | None
    text_content: str
    media_type: str
    media_group_id: str | None
    has_spoiler: bool
    view_count: int | None
    forward_count: int | None
    message_url: str | None
    hashtags: tuple[tuple[str, str], ...]
    links: tuple[tuple[str, str, bool], ...]
    prompt: PromptSignals


@dataclass(frozen=True, slots=True)
class ChannelOverview:
    channel_id: int
    total_messages: int
    total_publications: int
    prompt_publications: int
    media_messages: int
    spoiler_messages: int
    edited_messages: int
    total_hashtag_uses: int
    unique_hashtags: int
    unique_characters: int
    total_links: int
    telegram_links: int
    first_post_at: datetime | None
    last_post_at: datetime | None
    average_text_length: float
    captured_views: int
    captured_forwards: int


@dataclass(frozen=True, slots=True)
class HashtagStat:
    hashtag: str
    normalized_hashtag: str
    publication_count: int
    prompt_count: int
    last_used_at: datetime | None
    character_name: str | None


@dataclass(frozen=True, slots=True)
class CharacterUsageStat:
    character_id: int
    name: str
    publication_count: int
    prompt_count: int
    last_used_at: datetime | None
    category: str | None
    universe: str | None
    story_short_label: str | None
    story_title: str | None


@dataclass(frozen=True, slots=True)
class PromptStructureStats:
    prompt_publications: int
    with_important: int
    with_strict: int
    with_negative: int
    with_technical: int
    with_palette: int
    average_prompt_length: float


@dataclass(frozen=True, slots=True)
class NamedCount:
    name: str
    count: int


def normalize_hashtag(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().lstrip("#").casefold()


def compact_identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def extract_hashtags(text: str) -> tuple[tuple[str, str], ...]:
    unique: dict[str, str] = {}
    for match in _HASHTAG_RE.finditer(text):
        display = match.group(1)
        normalized = normalize_hashtag(display)
        if normalized and normalized not in unique:
            unique[normalized] = display
    return tuple((display, normalized) for normalized, display in unique.items())


def extract_links(text: str) -> tuple[tuple[str, str, bool], ...]:
    unique: dict[str, tuple[str, bool]] = {}
    for match in _URL_RE.finditer(text):
        value = match.group(0).rstrip(".,;:!?")
        url = value if value.casefold().startswith(("http://", "https://")) else f"https://{value}"
        parsed = urlparse(url)
        domain = (parsed.hostname or "").casefold()
        if not domain:
            continue
        unique[url] = (domain, domain in {"t.me", "telegram.me"})
    return tuple((url, domain, is_telegram) for url, (domain, is_telegram) in unique.items())


def analyze_prompt_text(text: str) -> PromptSignals:
    lowered = unicodedata.normalize("NFKC", text).casefold()
    has_important = bool(re.search(r"(?:^|\n)\s*(?:важно|important)\s*:?", lowered))
    has_strict = bool(re.search(r"(?:^|\n)\s*(?:строго|strict)\s*:?", lowered))
    has_negative = any(
        marker in lowered
        for marker in ("negative prompt", "negative:", "негативный промт", "запрещено:")
    )
    has_technical = any(
        marker in lowered
        for marker in (
            "техблок",
            "технический блок",
            "📷",
            "объектив",
            "shallow dof",
            "film grain",
            "9:16",
            "f/1.",
            "f/2.",
            "f/4",
            "f/8",
        )
    )
    has_palette = len(_HEX_RE.findall(text)) >= 3

    score = 0
    score += 3 if has_important else 0
    score += 3 if has_strict else 0
    score += 1 if has_negative else 0
    score += 1 if has_technical else 0
    score += 1 if has_palette else 0
    score += 2 if "референс" in lowered or "reference" in lowered else 0
    score += 1 if "композиция" in lowered or "поза" in lowered else 0
    score += 1 if len(text) >= 800 else 0

    return PromptSignals(
        is_prompt=(has_important and has_strict) or score >= 5,
        score=score,
        has_important=has_important,
        has_strict=has_strict,
        has_negative=has_negative,
        has_technical=has_technical,
        has_palette=has_palette,
    )


def detect_media_type(message: Any) -> str:
    for field in (
        "photo",
        "video",
        "animation",
        "document",
        "audio",
        "voice",
        "video_note",
        "sticker",
        "poll",
    ):
        if getattr(message, field, None):
            return field
    return "text"


def parse_channel_post(message: Message) -> ParsedChannelPost:
    text_content = message.text or message.caption or ""
    media_group_id = str(message.media_group_id) if message.media_group_id else None
    publication_key = (
        f"album:{media_group_id}"
        if media_group_id
        else f"message:{message.message_id}"
    )
    username = message.chat.username
    message_url = (
        f"https://t.me/{username}/{message.message_id}"
        if username
        else None
    )
    return ParsedChannelPost(
        channel_id=message.chat.id,
        message_id=message.message_id,
        publication_key=publication_key,
        posted_at=message.date,
        edited_at=message.edit_date,
        title=message.chat.title,
        username=username,
        author_signature=message.author_signature,
        text_content=text_content,
        media_type=detect_media_type(message),
        media_group_id=media_group_id,
        has_spoiler=bool(getattr(message, "has_media_spoiler", False)),
        view_count=message.views,
        forward_count=message.forward_count,
        message_url=message_url,
        hashtags=extract_hashtags(text_content),
        links=extract_links(text_content),
        prompt=analyze_prompt_text(text_content),
    )


async def ingest_channel_post(
    database: Database,
    message: Message,
) -> ParsedChannelPost:
    parsed = parse_channel_post(message)
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO tracked_channels (
                    chat_id, title, username, enabled, last_post_at, updated_at
                )
                VALUES ($1, $2, $3, TRUE, $4, NOW())
                ON CONFLICT (chat_id) DO UPDATE
                SET title = EXCLUDED.title,
                    username = EXCLUDED.username,
                    enabled = TRUE,
                    last_post_at = GREATEST(
                        tracked_channels.last_post_at,
                        EXCLUDED.last_post_at
                    ),
                    updated_at = NOW()
                """,
                parsed.channel_id,
                parsed.title,
                parsed.username,
                parsed.posted_at,
            )
            post_id = await connection.fetchval(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at, edited_at,
                    author_signature, text_content, text_length, media_type,
                    media_group_id, has_spoiler, view_count, forward_count,
                    is_prompt, prompt_score, has_important_section,
                    has_strict_section, has_negative_section,
                    has_technical_section, has_palette, message_url, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9,
                    $10, $11, $12, $13,
                    $14, $15, $16,
                    $17, $18,
                    $19, $20, $21, NOW()
                )
                ON CONFLICT (channel_id, message_id) DO UPDATE
                SET publication_key = EXCLUDED.publication_key,
                    posted_at = EXCLUDED.posted_at,
                    edited_at = EXCLUDED.edited_at,
                    author_signature = EXCLUDED.author_signature,
                    text_content = EXCLUDED.text_content,
                    text_length = EXCLUDED.text_length,
                    media_type = EXCLUDED.media_type,
                    media_group_id = EXCLUDED.media_group_id,
                    has_spoiler = EXCLUDED.has_spoiler,
                    view_count = EXCLUDED.view_count,
                    forward_count = EXCLUDED.forward_count,
                    is_prompt = EXCLUDED.is_prompt,
                    prompt_score = EXCLUDED.prompt_score,
                    has_important_section = EXCLUDED.has_important_section,
                    has_strict_section = EXCLUDED.has_strict_section,
                    has_negative_section = EXCLUDED.has_negative_section,
                    has_technical_section = EXCLUDED.has_technical_section,
                    has_palette = EXCLUDED.has_palette,
                    message_url = EXCLUDED.message_url,
                    updated_at = NOW()
                RETURNING id
                """,
                parsed.channel_id,
                parsed.message_id,
                parsed.publication_key,
                parsed.posted_at,
                parsed.edited_at,
                parsed.author_signature,
                parsed.text_content,
                len(parsed.text_content),
                parsed.media_type,
                parsed.media_group_id,
                parsed.has_spoiler,
                parsed.view_count,
                parsed.forward_count,
                parsed.prompt.is_prompt,
                parsed.prompt.score,
                parsed.prompt.has_important,
                parsed.prompt.has_strict,
                parsed.prompt.has_negative,
                parsed.prompt.has_technical,
                parsed.prompt.has_palette,
                parsed.message_url,
            )
            if post_id is None:
                raise RuntimeError("Не удалось сохранить пост канала.")

            await connection.execute(
                "DELETE FROM channel_post_hashtags WHERE post_id = $1",
                post_id,
            )
            await connection.execute(
                "DELETE FROM channel_post_links WHERE post_id = $1",
                post_id,
            )

            character_rows = await connection.fetch(
                "SELECT id, name, normalized_name FROM characters"
            )
            character_by_alias = {
                compact_identity(str(row["normalized_name"])): (
                    int(row["id"]),
                    str(row["name"]),
                )
                for row in character_rows
            }
            for display, normalized in parsed.hashtags:
                character = character_by_alias.get(compact_identity(normalized))
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
                    character[0] if character else None,
                    character is not None,
                )

            for url, domain, is_telegram in parsed.links:
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
    return parsed


async def get_channel_overview(
    database: Database,
    channel_id: int,
) -> ChannelOverview:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                COUNT(*) AS total_messages,
                COUNT(DISTINCT publication_key) AS total_publications,
                COUNT(DISTINCT publication_key) FILTER (WHERE is_prompt)
                    AS prompt_publications,
                COUNT(*) FILTER (WHERE media_type <> 'text') AS media_messages,
                COUNT(*) FILTER (WHERE has_spoiler) AS spoiler_messages,
                COUNT(*) FILTER (WHERE edited_at IS NOT NULL) AS edited_messages,
                MIN(posted_at) AS first_post_at,
                MAX(posted_at) AS last_post_at,
                COALESCE(AVG(text_length) FILTER (WHERE text_length > 0), 0)
                    AS average_text_length,
                COALESCE(SUM(view_count), 0) AS captured_views,
                COALESCE(SUM(forward_count), 0) AS captured_forwards
            FROM channel_posts
            WHERE channel_id = $1
            """,
            channel_id,
        )
        hashtag_row = await connection.fetchrow(
            """
            SELECT
                COUNT(*) AS total_hashtag_uses,
                COUNT(DISTINCT h.normalized_hashtag) AS unique_hashtags,
                COUNT(DISTINCT h.character_id) FILTER (
                    WHERE h.character_id IS NOT NULL
                ) AS unique_characters
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            WHERE p.channel_id = $1
            """,
            channel_id,
        )
        link_row = await connection.fetchrow(
            """
            SELECT
                COUNT(*) AS total_links,
                COUNT(*) FILTER (WHERE l.is_telegram) AS telegram_links
            FROM channel_post_links AS l
            JOIN channel_posts AS p ON p.id = l.post_id
            WHERE p.channel_id = $1
            """,
            channel_id,
        )

    return ChannelOverview(
        channel_id=channel_id,
        total_messages=int(row["total_messages"] or 0),
        total_publications=int(row["total_publications"] or 0),
        prompt_publications=int(row["prompt_publications"] or 0),
        media_messages=int(row["media_messages"] or 0),
        spoiler_messages=int(row["spoiler_messages"] or 0),
        edited_messages=int(row["edited_messages"] or 0),
        total_hashtag_uses=int(hashtag_row["total_hashtag_uses"] or 0),
        unique_hashtags=int(hashtag_row["unique_hashtags"] or 0),
        unique_characters=int(hashtag_row["unique_characters"] or 0),
        total_links=int(link_row["total_links"] or 0),
        telegram_links=int(link_row["telegram_links"] or 0),
        first_post_at=row["first_post_at"],
        last_post_at=row["last_post_at"],
        average_text_length=float(row["average_text_length"] or 0),
        captured_views=int(row["captured_views"] or 0),
        captured_forwards=int(row["captured_forwards"] or 0),
    )


async def list_hashtag_stats(
    database: Database,
    channel_id: int,
    *,
    limit: int = 20,
    prompt_only: bool = False,
) -> list[HashtagStat]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                MAX(h.hashtag) AS hashtag,
                h.normalized_hashtag,
                COUNT(DISTINCT p.publication_key) AS publication_count,
                COUNT(DISTINCT p.publication_key) FILTER (WHERE p.is_prompt)
                    AS prompt_count,
                MAX(p.posted_at) AS last_used_at,
                MAX(c.name) AS character_name
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            LEFT JOIN characters AS c ON c.id = h.character_id
            WHERE p.channel_id = $1
              AND ($2::BOOLEAN = FALSE OR p.is_prompt)
            GROUP BY h.normalized_hashtag
            ORDER BY publication_count DESC, last_used_at DESC, h.normalized_hashtag
            LIMIT $3
            """,
            channel_id,
            prompt_only,
            max(1, min(limit, 100)),
        )
    return [
        HashtagStat(
            hashtag=str(row["hashtag"]),
            normalized_hashtag=str(row["normalized_hashtag"]),
            publication_count=int(row["publication_count"] or 0),
            prompt_count=int(row["prompt_count"] or 0),
            last_used_at=row["last_used_at"],
            character_name=row["character_name"],
        )
        for row in rows
    ]


async def get_hashtag_stat(
    database: Database,
    channel_id: int,
    hashtag: str,
) -> HashtagStat | None:
    normalized = normalize_hashtag(hashtag)
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                MAX(h.hashtag) AS hashtag,
                h.normalized_hashtag,
                COUNT(DISTINCT p.publication_key) AS publication_count,
                COUNT(DISTINCT p.publication_key) FILTER (WHERE p.is_prompt)
                    AS prompt_count,
                MAX(p.posted_at) AS last_used_at,
                MAX(c.name) AS character_name
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            LEFT JOIN characters AS c ON c.id = h.character_id
            WHERE p.channel_id = $1
              AND h.normalized_hashtag = $2
            GROUP BY h.normalized_hashtag
            """,
            channel_id,
            normalized,
        )
    if row is None:
        return None
    return HashtagStat(
        hashtag=str(row["hashtag"]),
        normalized_hashtag=str(row["normalized_hashtag"]),
        publication_count=int(row["publication_count"] or 0),
        prompt_count=int(row["prompt_count"] or 0),
        last_used_at=row["last_used_at"],
        character_name=row["character_name"],
    )


async def list_character_usage_stats(
    database: Database,
    channel_id: int,
    *,
    limit: int = 20,
) -> list[CharacterUsageStat]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                c.id AS character_id,
                c.name,
                c.category,
                c.universe,
                s.short_label AS story_short_label,
                s.title AS story_title,
                COUNT(DISTINCT p.publication_key) AS publication_count,
                COUNT(DISTINCT p.publication_key) FILTER (WHERE p.is_prompt)
                    AS prompt_count,
                MAX(p.posted_at) AS last_used_at
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            JOIN characters AS c ON c.id = h.character_id
            LEFT JOIN character_stories AS s ON s.id = c.story_id
            WHERE p.channel_id = $1
            GROUP BY c.id, s.id
            ORDER BY publication_count DESC, last_used_at DESC, c.name
            LIMIT $2
            """,
            channel_id,
            max(1, min(limit, 100)),
        )
    return [
        CharacterUsageStat(
            character_id=int(row["character_id"]),
            name=str(row["name"]),
            publication_count=int(row["publication_count"] or 0),
            prompt_count=int(row["prompt_count"] or 0),
            last_used_at=row["last_used_at"],
            category=row["category"],
            universe=row["universe"],
            story_short_label=row["story_short_label"],
            story_title=row["story_title"],
        )
        for row in rows
    ]


async def get_prompt_structure_stats(
    database: Database,
    channel_id: int,
) -> PromptStructureStats:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                COUNT(DISTINCT publication_key) FILTER (WHERE is_prompt)
                    AS prompt_publications,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_important_section
                ) AS with_important,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_strict_section
                ) AS with_strict,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_negative_section
                ) AS with_negative,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_technical_section
                ) AS with_technical,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_palette
                ) AS with_palette,
                COALESCE(AVG(text_length) FILTER (WHERE is_prompt), 0)
                    AS average_prompt_length
            FROM channel_posts
            WHERE channel_id = $1
            """,
            channel_id,
        )
    return PromptStructureStats(
        prompt_publications=int(row["prompt_publications"] or 0),
        with_important=int(row["with_important"] or 0),
        with_strict=int(row["with_strict"] or 0),
        with_negative=int(row["with_negative"] or 0),
        with_technical=int(row["with_technical"] or 0),
        with_palette=int(row["with_palette"] or 0),
        average_prompt_length=float(row["average_prompt_length"] or 0),
    )


async def list_media_type_stats(
    database: Database,
    channel_id: int,
) -> list[NamedCount]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT media_type AS name, COUNT(*) AS count
            FROM channel_posts
            WHERE channel_id = $1
            GROUP BY media_type
            ORDER BY count DESC, media_type
            """,
            channel_id,
        )
    return [NamedCount(str(row["name"]), int(row["count"])) for row in rows]


async def list_link_domain_stats(
    database: Database,
    channel_id: int,
    *,
    limit: int = 10,
) -> list[NamedCount]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT l.domain AS name, COUNT(*) AS count
            FROM channel_post_links AS l
            JOIN channel_posts AS p ON p.id = l.post_id
            WHERE p.channel_id = $1
            GROUP BY l.domain
            ORDER BY count DESC, l.domain
            LIMIT $2
            """,
            channel_id,
            max(1, min(limit, 50)),
        )
    return [NamedCount(str(row["name"]), int(row["count"])) for row in rows]
