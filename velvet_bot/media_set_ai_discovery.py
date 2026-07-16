from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import velvet_bot.media_sets as media_sets
from velvet_bot.ai_vision import (
    build_semantic_reason,
    build_semantic_set_title,
    compare_semantic_profiles,
)
from velvet_bot.database import Database

_MIN_AI_SIMILARITY = 55
_MAX_SET_ITEMS = 12
_ORIGINAL_DISCOVER = media_sets.discover_media_set_candidates
_INSTALLED = False


@dataclass(frozen=True, slots=True)
class _AIContext:
    media_id: int
    characters: tuple[str, ...]
    profile: dict[str, Any]
    prompt_post_url: str | None


def _decode_profile(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
    return None


def _different_characters(first: _AIContext, second: _AIContext) -> bool:
    first_names = {value.casefold() for value in first.characters}
    second_names = {value.casefold() for value in second.characters}
    if not first_names or not second_names:
        return True
    return first_names != second_names


def _component_groups(items: tuple[_AIContext, ...]) -> tuple[tuple[_AIContext, ...], ...]:
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

    pair_scores: dict[tuple[int, int], int] = {}
    for first_index, first in enumerate(items):
        for second_index in range(first_index + 1, len(items)):
            second = items[second_index]
            if not _different_characters(first, second):
                continue
            match = compare_semantic_profiles(first.profile, second.profile)
            pair_scores[(first.media_id, second.media_id)] = match.score
            pair_scores[(second.media_id, first.media_id)] = match.score
            if match.score < _MIN_AI_SIMILARITY:
                continue
            if len(match.common_terms) < 2 and match.score < 70:
                continue
            union(first_index, second_index)

    grouped: dict[int, list[_AIContext]] = {}
    for index, item in enumerate(items):
        grouped.setdefault(find(index), []).append(item)

    result: list[tuple[_AIContext, ...]] = []
    for raw_group in grouped.values():
        if len(raw_group) < 2:
            continue
        group = sorted(raw_group, key=lambda item: item.media_id)
        if len(group) > 2:
            filtered: list[_AIContext] = []
            for item in group:
                scores = [
                    pair_scores.get((item.media_id, other.media_id), 0)
                    for other in group
                    if other.media_id != item.media_id
                ]
                average = round(sum(scores) / len(scores)) if scores else 0
                if average >= _MIN_AI_SIMILARITY:
                    filtered.append(item)
            group = filtered
        if len(group) >= 2:
            result.append(tuple(group[:_MAX_SET_ITEMS]))
    return tuple(result)


def _stable_candidate_key(items: tuple[_AIContext, ...]) -> str:
    ids = ":".join(str(item.media_id) for item in items)
    digest = hashlib.sha256(ids.encode("utf-8")).hexdigest()[:32]
    return f"ai:{digest}"


def _group_score(items: tuple[_AIContext, ...]) -> int:
    scores: list[int] = []
    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            scores.append(compare_semantic_profiles(first.profile, second.profile).score)
    return max(_MIN_AI_SIMILARITY, min(99, round(sum(scores) / len(scores)))) if scores else 0


def _item_score(item: _AIContext, items: tuple[_AIContext, ...]) -> int:
    scores = [
        compare_semantic_profiles(item.profile, other.profile).score
        for other in items
        if other.media_id != item.media_id
    ]
    return max(_MIN_AI_SIMILARITY, min(99, round(sum(scores) / len(scores)))) if scores else 0


def _common_prompt(items: tuple[_AIContext, ...]) -> str | None:
    values = {item.prompt_post_url for item in items if item.prompt_post_url}
    return next(iter(values)) if len(values) == 1 else None


async def _load_ai_contexts(database: Database, *, limit: int) -> tuple[_AIContext, ...]:
    safe_limit = max(20, min(int(limit), 1000))
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                mf.id AS media_id,
                profile.analysis,
                MAX(cm.prompt_post_url) FILTER (WHERE cm.prompt_post_url IS NOT NULL)
                    AS prompt_post_url,
                COALESCE(
                    ARRAY_AGG(DISTINCT c.name ORDER BY c.name)
                        FILTER (WHERE c.id IS NOT NULL),
                    ARRAY[]::VARCHAR[]
                ) AS characters
            FROM media_files AS mf
            JOIN media_ai_profiles AS profile
              ON profile.media_id = mf.id
             AND profile.status = 'ready'
            JOIN character_media AS cm ON cm.media_id = mf.id
            LEFT JOIN characters AS c ON c.id = cm.character_id
            WHERE mf.media_set_id IS NULL
              AND (
                    mf.media_type = 'photo'
                    OR (mf.media_type = 'document'
                        AND COALESCE(mf.mime_type, '') LIKE 'image/%')
                  )
            GROUP BY mf.id, profile.analysis, profile.analyzed_at
            ORDER BY profile.analyzed_at DESC NULLS LAST, mf.id DESC
            LIMIT $1::INTEGER
            """,
            safe_limit,
        )
    contexts: list[_AIContext] = []
    for row in rows:
        profile = _decode_profile(row["analysis"])
        if profile is None:
            continue
        contexts.append(
            _AIContext(
                media_id=int(row["media_id"]),
                characters=tuple(str(value) for value in row["characters"] if value),
                profile=profile,
                prompt_post_url=row["prompt_post_url"],
            )
        )
    return tuple(contexts)


async def _store_ai_candidates(
    database: Database,
    groups: tuple[tuple[_AIContext, ...], ...],
) -> int:
    created = 0
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            if groups:
                await connection.execute(
                    """
                    UPDATE media_set_candidates
                    SET status = 'ignored', decided_at = NOW(), updated_at = NOW(),
                        reason = reason || ' Заменено глубоким ИИ-анализом.'
                    WHERE status = 'pending'
                      AND (
                            candidate_key LIKE 'filename:%'
                            OR candidate_key LIKE 'context:%'
                          )
                    """
                )
            for items in groups:
                profiles = [item.profile for item in items]
                score = _group_score(items)
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
                    _stable_candidate_key(items),
                    build_semantic_set_title(profiles)[:160],
                    build_semantic_reason(profiles),
                    score,
                    _common_prompt(items),
                )
                if candidate_row is None:
                    continue
                candidate_id = int(candidate_row["id"])
                created += int(bool(candidate_row["inserted"]))
                for item in items:
                    match_terms: set[str] = set()
                    for other in items:
                        if other.media_id == item.media_id:
                            continue
                        match_terms.update(
                            compare_semantic_profiles(
                                item.profile,
                                other.profile,
                            ).common_terms
                        )
                    reason = (
                        "ИИ-контекст: " + ", ".join(sorted(match_terms)[:6])
                        if match_terms
                        else "Совпадение смыслового профиля"
                    )
                    await connection.execute(
                        """
                        INSERT INTO media_set_candidate_items (
                            candidate_id, media_id, selected, context_score, reason
                        )
                        SELECT $1::BIGINT, $2::BIGINT, TRUE, $3::SMALLINT, $4::TEXT
                        WHERE EXISTS (
                            SELECT 1 FROM media_files
                            WHERE id = $2::BIGINT AND media_set_id IS NULL
                        )
                        ON CONFLICT (candidate_id, media_id) DO UPDATE
                        SET context_score = EXCLUDED.context_score,
                            reason = EXCLUDED.reason
                        """,
                        candidate_id,
                        item.media_id,
                        _item_score(item, items),
                        reason[:500],
                    )
    return created


async def discover_media_set_candidates_with_ai(
    database: Database,
    *,
    limit: int = 300,
) -> int:
    # Keep exact shared-prompt and manually-created visual proposals from the
    # existing detector. Weak filename/time proposals are retired below once
    # semantic profiles are available.
    fallback_created = await _ORIGINAL_DISCOVER(database, limit=limit)
    contexts = await _load_ai_contexts(database, limit=max(limit, 600))
    if len(contexts) < 2:
        return fallback_created
    groups = _component_groups(contexts)
    ai_created = await _store_ai_candidates(database, groups)
    return fallback_created + ai_created


def install_ai_media_set_discovery() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    media_sets.discover_media_set_candidates = discover_media_set_candidates_with_ai
    _INSTALLED = True


install_ai_media_set_discovery()


__all__ = (
    "discover_media_set_candidates_with_ai",
    "install_ai_media_set_discovery",
)
