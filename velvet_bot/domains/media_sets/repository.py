from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class MediaSetCandidateIdPage:
    ids: tuple[int, ...]
    page: int
    page_size: int
    total_items: int


class MediaSetCandidateListingRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_ids(
        self,
        *,
        status: str,
        page: int,
        page_size: int,
    ) -> MediaSetCandidateIdPage:
        safe_size = max(1, min(int(page_size), 8))
        safe_page = max(0, int(page))
        async with self._database.acquire() as connection:
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT candidate.id
                        FROM media_set_candidates AS candidate
                        JOIN media_set_candidate_items AS item
                          ON item.candidate_id = candidate.id
                        JOIN media_files AS media ON media.id = item.media_id
                        WHERE candidate.status = $1::VARCHAR
                          AND media.media_set_id IS NULL
                        GROUP BY candidate.id
                        HAVING COUNT(*) >= 2
                    ) AS available_candidates
                    """,
                    status,
                )
                or 0
            )
            total_pages = max(1, (total + safe_size - 1) // safe_size)
            normalized_page = min(safe_page, total_pages - 1)
            rows = await connection.fetch(
                """
                SELECT candidate.id, COUNT(*) AS available_item_count
                FROM media_set_candidates AS candidate
                JOIN media_set_candidate_items AS item
                  ON item.candidate_id = candidate.id
                JOIN media_files AS media ON media.id = item.media_id
                WHERE candidate.status = $1::VARCHAR
                  AND media.media_set_id IS NULL
                GROUP BY candidate.id, candidate.score
                HAVING COUNT(*) >= 2
                ORDER BY available_item_count DESC, candidate.score DESC, candidate.id
                OFFSET $2::INTEGER LIMIT $3::INTEGER
                """,
                status,
                normalized_page * safe_size,
                safe_size,
            )
        return MediaSetCandidateIdPage(
            ids=tuple(int(row["id"]) for row in rows),
            page=normalized_page,
            page_size=safe_size,
            total_items=total,
        )


__all__ = (
    "MediaSetCandidateIdPage",
    "MediaSetCandidateListingRepository",
)
