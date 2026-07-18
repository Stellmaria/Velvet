from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class MediaSetAIContextRow:
    media_id: int
    characters: tuple[str, ...]
    analysis: Any
    prompt_post_url: str | None


@dataclass(frozen=True, slots=True)
class MediaSetAICandidateItemDraft:
    media_id: int
    context_score: int
    reason: str


@dataclass(frozen=True, slots=True)
class MediaSetAICandidateDraft:
    candidate_key: str
    suggested_title: str
    reason: str
    score: int
    prompt_post_url: str | None
    items: tuple[MediaSetAICandidateItemDraft, ...]


class MediaSetAIRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def load_context_rows(self, *, limit: int) -> tuple[MediaSetAIContextRow, ...]:
        safe_limit = max(20, min(int(limit), 1000))
        async with self._database.acquire() as connection:
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
        return tuple(
            MediaSetAIContextRow(
                media_id=int(row["media_id"]),
                characters=tuple(str(value) for value in row["characters"] if value),
                analysis=row["analysis"],
                prompt_post_url=row["prompt_post_url"],
            )
            for row in rows
        )

    async def store_candidates(
        self,
        candidates: tuple[MediaSetAICandidateDraft, ...],
    ) -> int:
        created = 0
        async with self._database.acquire() as connection:
            async with connection.transaction():
                if candidates:
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
                for candidate in candidates:
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
                        candidate.candidate_key,
                        candidate.suggested_title,
                        candidate.reason,
                        candidate.score,
                        candidate.prompt_post_url,
                    )
                    if candidate_row is None:
                        continue
                    candidate_id = int(candidate_row["id"])
                    created += int(bool(candidate_row["inserted"]))
                    for item in candidate.items:
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
                            item.context_score,
                            item.reason,
                        )
        return created


__all__ = (
    "MediaSetAICandidateDraft",
    "MediaSetAICandidateItemDraft",
    "MediaSetAIContextRow",
    "MediaSetAIRepository",
)
