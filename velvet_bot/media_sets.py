from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from velvet_bot.database import Database
from velvet_bot.visual_fingerprint import hamming_distance

_CONTEXT_WINDOW_SECONDS = 20 * 60
_MAX_SET_ITEMS = 12
_GENERATED_SUFFIX_RE = re.compile(r"__[0-9a-f]{16,64}$", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\wа-яё]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MediaSetCandidateItem:
    media_id: int
    telegram_file_id: str
    media_type: str
    file_name: str
    characters: tuple[str, ...]
    selected: bool
    context_score: int
    reason: str | None


@dataclass(frozen=True, slots=True)
class MediaSetCandidate:
    id: int
    suggested_title: str
    reason: str
    score: int
    prompt_post_url: str | None
    status: str
    items: tuple[MediaSetCandidateItem, ...]

    @property
    def selected_count(self) -> int:
        return sum(item.selected for item in self.items)


@dataclass(frozen=True, slots=True)
class MediaSetCandidatePage:
    items: tuple[MediaSetCandidate, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


@dataclass(frozen=True, slots=True)
class CreatedMediaSet:
    id: int
    title: str
    media_ids: tuple[int, ...]
    prompt_post_url: str | None


@dataclass(frozen=True, slots=True)
class ArchiveMessageReference:
    chat_id: int
    message_id: int
    character_name: str


@dataclass(frozen=True, slots=True)
class DeletedDuplicateMedia:
    media_id: int
    file_name: str
    characters: tuple[str, ...]
    archive_messages: tuple[ArchiveMessageReference, ...]


@dataclass(frozen=True, slots=True)
class _MediaContext:
    media_id: int
    telegram_file_id: str
    media_type: str
    file_name: str
    linked_at: datetime
    characters: tuple[str, ...]
    universes: tuple[str, ...]
    story_ids: tuple[int, ...]
    prompt_post_url: str | None
    width: int | None
    height: int | None
    phash: str | None

    @property
    def aspect_ratio(self) -> float | None:
        if not self.width or not self.height:
            return None
        return self.width / self.height


@dataclass(frozen=True, slots=True)
class _CandidateDraft:
    key: str
    title: str
    reason: str
    score: int
    prompt_post_url: str | None
    items: tuple[tuple[int, int, str], ...]


def _stable_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _filename_family(file_name: str, characters: tuple[str, ...]) -> str:
    stem = _GENERATED_SUFFIX_RE.sub("", Path(file_name).stem.casefold())
    for character in sorted(characters, key=len, reverse=True):
        normalized = _WORD_RE.sub(" ", character.casefold()).strip()
        if normalized:
            stem = stem.replace(normalized, " ")
    words = [word for word in _WORD_RE.sub(" ", stem).split() if not word.isdigit()]
    return " ".join(words).strip()


def _same_story_context(first: _MediaContext, second: _MediaContext) -> bool:
    if set(first.story_ids) & set(second.story_ids):
        return True
    return bool(set(first.universes) & set(second.universes))


def _visual_context_score(first: _MediaContext, second: _MediaContext) -> int:
    score = 0
    first_ratio = first.aspect_ratio
    second_ratio = second.aspect_ratio
    if first_ratio is not None and second_ratio is not None:
        ratio_delta = abs(first_ratio - second_ratio)
        if ratio_delta <= 0.04:
            score += 18
        elif ratio_delta <= 0.12:
            score += 10
        elif ratio_delta > 0.22:
            return 0
    if first.phash and second.phash:
        distance = hamming_distance(first.phash, second.phash)
        if distance <= 10:
            score += 35
        elif distance <= 18:
            score += 24
        elif distance <= 26:
            score += 12
    return score


def _build_context_components(items: tuple[_MediaContext, ...]) -> tuple[tuple[_MediaContext, ...], ...]:
    if len(items) < 2:
        return ()
    parents = list(range(len(items)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first_index: int, second_index: int) -> None:
        first_root = find(first_index)
        second_root = find(second_index)
        if first_root != second_root:
            parents[second_root] = first_root

    for first_index, first in enumerate(items):
        for second_index in range(first_index + 1, len(items)):
            second = items[second_index]
            if first.media_type != second.media_type:
                continue
            if set(first.characters) == set(second.characters):
                continue
            seconds = abs((first.linked_at - second.linked_at).total_seconds())
            if seconds > _CONTEXT_WINDOW_SECONDS:
                continue
            if not _same_story_context(first, second):
                continue
            family_match = bool(
                _filename_family(first.file_name, first.characters)
                and _filename_family(first.file_name, first.characters)
                == _filename_family(second.file_name, second.characters)
            )
            visual_score = _visual_context_score(first, second)
            if not family_match and visual_score < 12:
                continue
            union(first_index, second_index)

    grouped: dict[int, list[_MediaContext]] = {}
    for index, item in enumerate(items):
        grouped.setdefault(find(index), []).append(item)
    return tuple(
        tuple(sorted(component, key=lambda item: item.media_id))
        for component in grouped.values()
        if len(component) >= 2
    )


def _context_title(items: tuple[_MediaContext, ...]) -> str:
    universes = sorted({value for item in items for value in item.universes})
    characters = sorted({value for item in items for value in item.characters})
    if universes:
        base = universes[0].upper()
    else:
        base = "Контекст"
    names = ", ".join(characters[:3])
    suffix = f": {names}" if names else ""
    return f"{base} · сет{suffix}"[:160]


def _drafts_from_contexts(items: tuple[_MediaContext, ...]) -> tuple[_CandidateDraft, ...]:
    drafts: list[_CandidateDraft] = []
    prompt_groups: dict[str, list[_MediaContext]] = {}
    filename_groups: dict[tuple[str, str], list[_MediaContext]] = {}

    for item in items:
        if item.prompt_post_url:
            prompt_groups.setdefault(item.prompt_post_url, []).append(item)
        family = _filename_family(item.file_name, item.characters)
        universe_key = ",".join(sorted(item.universes))
        if len(family) >= 4:
            filename_groups.setdefault((universe_key, family), []).append(item)

    claimed: set[int] = set()
    for prompt_url, group in prompt_groups.items():
        unique = tuple(sorted({item.media_id: item for item in group}.values(), key=lambda item: item.media_id))
        if len(unique) < 2:
            continue
        unique = unique[:_MAX_SET_ITEMS]
        claimed.update(item.media_id for item in unique)
        drafts.append(
            _CandidateDraft(
                key=_stable_key("prompt", prompt_url),
                title=_context_title(unique),
                reason="У материалов уже указана одна и та же ссылка на промт.",
                score=100,
                prompt_post_url=prompt_url,
                items=tuple((item.media_id, 100, "Общий промт") for item in unique),
            )
        )

    for (universe_key, family), group in filename_groups.items():
        unique = tuple(sorted({item.media_id: item for item in group}.values(), key=lambda item: item.media_id))
        if len(unique) < 2 or all(item.media_id in claimed for item in unique):
            continue
        unique = unique[:_MAX_SET_ITEMS]
        key_source = f"{universe_key}|{family}"
        drafts.append(
            _CandidateDraft(
                key=_stable_key("filename", key_source),
                title=(family.title() or _context_title(unique))[:160],
                reason="Совпадает семейство имён файлов после удаления имён персонажей.",
                score=90,
                prompt_post_url=next((item.prompt_post_url for item in unique if item.prompt_post_url), None),
                items=tuple((item.media_id, 90, "Общее имя серии") for item in unique),
            )
        )
        claimed.update(item.media_id for item in unique)

    remaining = tuple(item for item in items if item.media_id not in claimed)
    for component in _build_context_components(remaining):
        component = component[:_MAX_SET_ITEMS]
        ids = [item.media_id for item in component]
        visual_scores: list[int] = []
        for index, first in enumerate(component):
            for second in component[index + 1 :]:
                visual_scores.append(_visual_context_score(first, second))
        average_visual = round(sum(visual_scores) / len(visual_scores)) if visual_scores else 0
        score = max(65, min(89, 65 + average_visual // 2))
        key_seed = ":".join(str(value) for value in ids[:2])
        drafts.append(
            _CandidateDraft(
                key=f"context:{key_seed}",
                title=_context_title(component),
                reason=(
                    "Материалы загружены рядом по времени, относятся к одной "
                    "вселенной или истории и имеют сходные визуальные признаки."
                ),
                score=score,
                prompt_post_url=next((item.prompt_post_url for item in component if item.prompt_post_url), None),
                items=tuple((item.media_id, score, "Общий контекст загрузки") for item in component),
            )
        )

    return tuple(drafts)


async def discover_media_set_candidates(database: Database, *, limit: int = 300) -> int:
    safe_limit = max(20, min(int(limit), 600))
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                mf.id AS media_id,
                mf.telegram_file_id,
                mf.media_type,
                COALESCE(mf.original_file_name, mf.storage_file_name) AS file_name,
                MIN(cm.created_at) AS linked_at,
                COALESCE(ARRAY_AGG(DISTINCT c.name ORDER BY c.name), ARRAY[]::VARCHAR[])
                    AS characters,
                COALESCE(ARRAY_REMOVE(ARRAY_AGG(DISTINCT c.universe), NULL), ARRAY[]::VARCHAR[])
                    AS universes,
                COALESCE(ARRAY_REMOVE(ARRAY_AGG(DISTINCT c.story_id), NULL), ARRAY[]::BIGINT[])
                    AS story_ids,
                MAX(cm.prompt_post_url) FILTER (WHERE cm.prompt_post_url IS NOT NULL)
                    AS prompt_post_url,
                fp.width,
                fp.height,
                fp.phash
            FROM media_files AS mf
            JOIN character_media AS cm ON cm.media_id = mf.id
            JOIN characters AS c ON c.id = cm.character_id
            LEFT JOIN media_visual_fingerprints AS fp ON fp.media_id = mf.id
            WHERE mf.media_set_id IS NULL
              AND (
                    mf.media_type = 'photo'
                    OR (mf.media_type = 'document' AND COALESCE(mf.mime_type, '') LIKE 'image/%')
                  )
            GROUP BY mf.id, fp.width, fp.height, fp.phash
            ORDER BY MIN(cm.created_at) DESC, mf.id DESC
            LIMIT $1::INTEGER
            """,
            safe_limit,
        )

    contexts = tuple(
        _MediaContext(
            media_id=int(row["media_id"]),
            telegram_file_id=str(row["telegram_file_id"]),
            media_type=str(row["media_type"]),
            file_name=str(row["file_name"]),
            linked_at=row["linked_at"],
            characters=tuple(str(value) for value in row["characters"]),
            universes=tuple(str(value) for value in row["universes"]),
            story_ids=tuple(int(value) for value in row["story_ids"]),
            prompt_post_url=row["prompt_post_url"],
            width=int(row["width"]) if row["width"] is not None else None,
            height=int(row["height"]) if row["height"] is not None else None,
            phash=str(row["phash"]) if row["phash"] is not None else None,
        )
        for row in rows
    )
    drafts = _drafts_from_contexts(contexts)
    created = 0
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            for draft in drafts:
                candidate_row = await connection.fetchrow(
                    """
                    INSERT INTO media_set_candidates (
                        candidate_key, suggested_title, reason, score,
                        prompt_post_url, status, updated_at
                    )
                    VALUES ($1::TEXT, $2::VARCHAR, $3::TEXT, $4::SMALLINT,
                            $5::TEXT, 'pending', NOW())
                    ON CONFLICT (candidate_key) DO UPDATE
                    SET suggested_title = EXCLUDED.suggested_title,
                        reason = EXCLUDED.reason,
                        score = EXCLUDED.score,
                        prompt_post_url = COALESCE(
                            media_set_candidates.prompt_post_url,
                            EXCLUDED.prompt_post_url
                        ),
                        updated_at = NOW()
                    WHERE media_set_candidates.status = 'pending'
                    RETURNING id, (xmax = 0) AS inserted
                    """,
                    draft.key,
                    draft.title,
                    draft.reason,
                    draft.score,
                    draft.prompt_post_url,
                )
                if candidate_row is None:
                    continue
                candidate_id = int(candidate_row["id"])
                created += int(bool(candidate_row["inserted"]))
                for media_id, context_score, reason in draft.items:
                    await connection.execute(
                        """
                        INSERT INTO media_set_candidate_items (
                            candidate_id, media_id, context_score, reason
                        )
                        SELECT $1::BIGINT, $2::BIGINT, $3::SMALLINT, $4::TEXT
                        WHERE EXISTS (
                            SELECT 1 FROM media_files
                            WHERE id = $2::BIGINT AND media_set_id IS NULL
                        )
                        ON CONFLICT (candidate_id, media_id) DO UPDATE
                        SET context_score = EXCLUDED.context_score,
                            reason = EXCLUDED.reason
                        """,
                        candidate_id,
                        media_id,
                        context_score,
                        reason,
                    )
    return created


async def list_media_set_candidates(
    database: Database,
    *,
    status: str = "pending",
    page: int = 0,
    page_size: int = 6,
) -> MediaSetCandidatePage:
    safe_size = max(1, min(int(page_size), 8))
    safe_page = max(0, int(page))
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM media_set_candidates WHERE status = $1::VARCHAR",
                status,
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        ids = await connection.fetch(
            """
            SELECT id
            FROM media_set_candidates
            WHERE status = $1::VARCHAR
            ORDER BY score DESC, id
            OFFSET $2::INTEGER LIMIT $3::INTEGER
            """,
            status,
            normalized_page * safe_size,
            safe_size,
        )
    candidates = []
    for row in ids:
        candidate = await get_media_set_candidate(database, int(row["id"]))
        if candidate is not None:
            candidates.append(candidate)
    return MediaSetCandidatePage(
        items=tuple(candidates),
        page=normalized_page,
        page_size=safe_size,
        total_items=total,
    )


async def get_media_set_candidate(
    database: Database,
    candidate_id: int,
) -> MediaSetCandidate | None:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id, suggested_title, reason, score, prompt_post_url, status
            FROM media_set_candidates
            WHERE id = $1::BIGINT
            """,
            int(candidate_id),
        )
        if row is None:
            return None
        item_rows = await connection.fetch(
            """
            SELECT
                sci.media_id,
                mf.telegram_file_id,
                mf.media_type,
                COALESCE(mf.original_file_name, mf.storage_file_name) AS file_name,
                sci.selected,
                sci.context_score,
                sci.reason,
                COALESCE(ARRAY_AGG(DISTINCT c.name ORDER BY c.name), ARRAY[]::VARCHAR[])
                    AS characters
            FROM media_set_candidate_items AS sci
            JOIN media_files AS mf ON mf.id = sci.media_id
            LEFT JOIN character_media AS cm ON cm.media_id = mf.id
            LEFT JOIN characters AS c ON c.id = cm.character_id
            WHERE sci.candidate_id = $1::BIGINT
              AND mf.media_set_id IS NULL
            GROUP BY sci.media_id, mf.id, sci.selected, sci.context_score, sci.reason
            ORDER BY sci.context_score DESC, sci.media_id
            """,
            int(candidate_id),
        )
    return MediaSetCandidate(
        id=int(row["id"]),
        suggested_title=str(row["suggested_title"]),
        reason=str(row["reason"]),
        score=int(row["score"]),
        prompt_post_url=row["prompt_post_url"],
        status=str(row["status"]),
        items=tuple(
            MediaSetCandidateItem(
                media_id=int(item["media_id"]),
                telegram_file_id=str(item["telegram_file_id"]),
                media_type=str(item["media_type"]),
                file_name=str(item["file_name"]),
                characters=tuple(str(value) for value in item["characters"] if value),
                selected=bool(item["selected"]),
                context_score=int(item["context_score"]),
                reason=item["reason"],
            )
            for item in item_rows
        ),
    )


async def toggle_media_set_candidate_item(
    database: Database,
    *,
    candidate_id: int,
    media_id: int,
) -> bool | None:
    async with database._require_pool().acquire() as connection:
        value = await connection.fetchval(
            """
            UPDATE media_set_candidate_items AS item
            SET selected = NOT item.selected
            FROM media_set_candidates AS candidate
            WHERE item.candidate_id = $1::BIGINT
              AND item.media_id = $2::BIGINT
              AND candidate.id = item.candidate_id
              AND candidate.status = 'pending'
            RETURNING item.selected
            """,
            int(candidate_id),
            int(media_id),
        )
    return bool(value) if value is not None else None


async def decide_media_set_candidate(
    database: Database,
    *,
    candidate_id: int,
    status: str,
    decided_by: int,
) -> bool:
    if status not in {"ignored", "pending"}:
        raise ValueError("Неизвестное решение по предложению сета.")
    async with database._require_pool().acquire() as connection:
        value = await connection.fetchval(
            """
            UPDATE media_set_candidates
            SET status = $2::VARCHAR,
                decided_by = CASE WHEN $2::VARCHAR = 'pending' THEN NULL ELSE $3::BIGINT END,
                decided_at = CASE WHEN $2::VARCHAR = 'pending' THEN NULL ELSE NOW() END,
                updated_at = NOW()
            WHERE id = $1::BIGINT
            RETURNING id
            """,
            int(candidate_id),
            status,
            int(decided_by),
        )
    return value is not None


async def create_media_set(
    database: Database,
    *,
    candidate_id: int,
    created_by: int,
) -> CreatedMediaSet:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            candidate = await connection.fetchrow(
                """
                SELECT id, suggested_title, prompt_post_url, status
                FROM media_set_candidates
                WHERE id = $1::BIGINT
                FOR UPDATE
                """,
                int(candidate_id),
            )
            if candidate is None:
                raise ValueError("Предложение сета больше не найдено.")
            if candidate["status"] != "pending":
                raise ValueError("Это предложение уже обработано.")
            item_rows = await connection.fetch(
                """
                SELECT item.media_id
                FROM media_set_candidate_items AS item
                JOIN media_files AS mf ON mf.id = item.media_id
                WHERE item.candidate_id = $1::BIGINT
                  AND item.selected = TRUE
                  AND mf.media_set_id IS NULL
                ORDER BY item.media_id
                FOR UPDATE OF mf
                """,
                int(candidate_id),
            )
            media_ids = tuple(int(row["media_id"]) for row in item_rows)
            if len(media_ids) < 2:
                raise ValueError("Для сета нужно выбрать минимум два материала.")
            set_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO media_sets (title, prompt_post_url, created_by)
                    VALUES ($1::VARCHAR, $2::TEXT, $3::BIGINT)
                    RETURNING id
                    """,
                    str(candidate["suggested_title"])[:160],
                    candidate["prompt_post_url"],
                    int(created_by),
                )
            )
            await connection.execute(
                """
                UPDATE media_files
                SET media_set_id = $1::BIGINT
                WHERE id = ANY($2::BIGINT[])
                  AND media_set_id IS NULL
                """,
                set_id,
                list(media_ids),
            )
            if candidate["prompt_post_url"] is not None:
                await connection.execute(
                    """
                    UPDATE character_media
                    SET prompt_post_url = $2::TEXT
                    WHERE media_id = ANY($1::BIGINT[])
                      AND prompt_post_url IS DISTINCT FROM $2::TEXT
                    """,
                    list(media_ids),
                    candidate["prompt_post_url"],
                )
            await connection.execute(
                """
                UPDATE media_set_candidates
                SET status = 'accepted',
                    decided_by = $2::BIGINT,
                    decided_at = NOW(),
                    created_set_id = $3::BIGINT,
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(candidate_id),
                int(created_by),
                set_id,
            )
    return CreatedMediaSet(
        id=set_id,
        title=str(candidate["suggested_title"]),
        media_ids=media_ids,
        prompt_post_url=candidate["prompt_post_url"],
    )


async def create_set_candidate_from_duplicate(
    database: Database,
    *,
    duplicate_candidate_id: int,
    decided_by: int,
) -> int:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                SELECT dc.first_media_id, dc.second_media_id, dc.similarity_score,
                       m1.media_set_id AS first_set_id,
                       m2.media_set_id AS second_set_id,
                       COALESCE(ARRAY_AGG(DISTINCT c.name ORDER BY c.name)
                           FILTER (WHERE c.id IS NOT NULL), ARRAY[]::VARCHAR[]) AS characters,
                       MAX(cm.prompt_post_url) FILTER (WHERE cm.prompt_post_url IS NOT NULL)
                           AS prompt_post_url
                FROM media_duplicate_candidates AS dc
                JOIN media_files AS m1 ON m1.id = dc.first_media_id
                JOIN media_files AS m2 ON m2.id = dc.second_media_id
                LEFT JOIN character_media AS cm
                    ON cm.media_id IN (dc.first_media_id, dc.second_media_id)
                LEFT JOIN characters AS c ON c.id = cm.character_id
                WHERE dc.id = $1::BIGINT
                GROUP BY dc.id, m1.media_set_id, m2.media_set_id
                FOR UPDATE OF dc
                """,
                int(duplicate_candidate_id),
            )
            if row is None:
                raise ValueError("Пара больше не найдена.")
            if row["first_set_id"] is not None or row["second_set_id"] is not None:
                raise ValueError("Один из материалов уже входит в сет.")
            media_ids = tuple(sorted((int(row["first_media_id"]), int(row["second_media_id"]))))
            characters = tuple(str(value) for value in row["characters"] if value)
            title = ("Сет: " + ", ".join(characters[:4]))[:160] if characters else "Новый медиасет"
            key = f"visual:{media_ids[0]}:{media_ids[1]}"
            candidate_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO media_set_candidates (
                        candidate_key, suggested_title, reason, score, prompt_post_url
                    )
                    VALUES ($1::TEXT, $2::VARCHAR, $3::TEXT, $4::SMALLINT, $5::TEXT)
                    ON CONFLICT (candidate_key) DO UPDATE
                    SET status = 'pending',
                        reason = EXCLUDED.reason,
                        score = EXCLUDED.score,
                        prompt_post_url = COALESCE(
                            media_set_candidates.prompt_post_url,
                            EXCLUDED.prompt_post_url
                        ),
                        decided_by = NULL,
                        decided_at = NULL,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    key,
                    title,
                    "Сходная композиция или стиль, но материалы решено не считать дублями.",
                    max(65, int(row["similarity_score"])),
                    row["prompt_post_url"],
                )
            )
            for media_id in media_ids:
                await connection.execute(
                    """
                    INSERT INTO media_set_candidate_items (
                        candidate_id, media_id, selected, context_score, reason
                    )
                    VALUES ($1::BIGINT, $2::BIGINT, TRUE, $3::SMALLINT, $4::TEXT)
                    ON CONFLICT (candidate_id, media_id) DO UPDATE
                    SET selected = TRUE,
                        context_score = EXCLUDED.context_score,
                        reason = EXCLUDED.reason
                    """,
                    candidate_id,
                    media_id,
                    max(65, int(row["similarity_score"])),
                    "Предложено из проверки похожей пары",
                )
            await connection.execute(
                """
                UPDATE media_duplicate_candidates
                SET status = 'ignored', decided_by = $2::BIGINT,
                    decided_at = NOW(), updated_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(duplicate_candidate_id),
                int(decided_by),
            )
    return candidate_id


async def delete_duplicate_media(
    database: Database,
    *,
    duplicate_candidate_id: int,
    media_id: int,
    decided_by: int,
) -> DeletedDuplicateMedia:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            candidate = await connection.fetchrow(
                """
                SELECT first_media_id, second_media_id
                FROM media_duplicate_candidates
                WHERE id = $1::BIGINT
                FOR UPDATE
                """,
                int(duplicate_candidate_id),
            )
            if candidate is None:
                raise ValueError("Пара дублей больше не найдена.")
            allowed_ids = {int(candidate["first_media_id"]), int(candidate["second_media_id"])}
            if int(media_id) not in allowed_ids:
                raise ValueError("Выбранный файл не относится к этой паре.")
            media_row = await connection.fetchrow(
                """
                SELECT COALESCE(original_file_name, storage_file_name) AS file_name,
                       media_set_id
                FROM media_files
                WHERE id = $1::BIGINT
                FOR UPDATE
                """,
                int(media_id),
            )
            if media_row is None:
                raise ValueError("Выбранный дубль уже удалён.")
            link_rows = await connection.fetch(
                """
                SELECT c.name AS character_name, c.archive_chat_id,
                       cm.archive_message_id
                FROM character_media AS cm
                JOIN characters AS c ON c.id = cm.character_id
                WHERE cm.media_id = $1::BIGINT
                ORDER BY c.normalized_name
                """,
                int(media_id),
            )
            characters = tuple(str(row["character_name"]) for row in link_rows)
            archive_messages = tuple(
                ArchiveMessageReference(
                    chat_id=int(row["archive_chat_id"]),
                    message_id=int(row["archive_message_id"]),
                    character_name=str(row["character_name"]),
                )
                for row in link_rows
                if row["archive_chat_id"] is not None
                and row["archive_message_id"] is not None
            )
            media_set_id = (
                int(media_row["media_set_id"])
                if media_row["media_set_id"] is not None
                else None
            )
            await connection.execute(
                "DELETE FROM media_duplicate_candidates "
                "WHERE first_media_id = $1::BIGINT OR second_media_id = $1::BIGINT",
                int(media_id),
            )
            await connection.execute(
                "DELETE FROM media_set_candidate_items WHERE media_id = $1::BIGINT",
                int(media_id),
            )
            await connection.execute(
                """
                DELETE FROM media_set_candidates AS candidate
                WHERE NOT EXISTS (
                    SELECT 1 FROM media_set_candidate_items AS item
                    WHERE item.candidate_id = candidate.id
                )
                  AND candidate.status = 'pending'
                """
            )
            await connection.execute(
                "DELETE FROM media_visual_fingerprints WHERE media_id = $1::BIGINT",
                int(media_id),
            )
            await connection.execute(
                "DELETE FROM media_file_checks WHERE media_id = $1::BIGINT",
                int(media_id),
            )
            await connection.execute(
                "DELETE FROM character_media WHERE media_id = $1::BIGINT",
                int(media_id),
            )
            await connection.execute(
                "DELETE FROM media_files WHERE id = $1::BIGINT",
                int(media_id),
            )
            if media_set_id is not None:
                await connection.execute(
                    """
                    DELETE FROM media_sets AS media_set
                    WHERE media_set.id = $1::BIGINT
                      AND NOT EXISTS (
                          SELECT 1 FROM media_files
                          WHERE media_set_id = media_set.id
                      )
                    """,
                    media_set_id,
                )
    return DeletedDuplicateMedia(
        media_id=int(media_id),
        file_name=str(media_row["file_name"]),
        characters=characters,
        archive_messages=archive_messages,
    )


__all__ = (
    "ArchiveMessageReference",
    "CreatedMediaSet",
    "DeletedDuplicateMedia",
    "MediaSetCandidate",
    "MediaSetCandidateItem",
    "MediaSetCandidatePage",
    "create_media_set",
    "create_set_candidate_from_duplicate",
    "decide_media_set_candidate",
    "delete_duplicate_media",
    "discover_media_set_candidates",
    "get_media_set_candidate",
    "list_media_set_candidates",
    "toggle_media_set_candidate_item",
)
