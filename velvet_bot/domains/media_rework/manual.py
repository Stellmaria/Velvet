from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID

_ACTIVE_STATUSES = ("needs_fix", "checking", "ready_for_review")


async def request_manual_rework(
    database: Database,
    *,
    media_id: int,
    user_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    reason: str = "Стэл отправила работу на доработку из публичного архива.",
) -> bool:
    """Create or reopen one workspace-scoped admin rework item."""

    scoped_workspace_id = int(workspace_id)
    async with database.acquire() as connection:
        async with connection.transaction():
            linked = await connection.fetchval(
                """
                SELECT TRUE
                FROM character_media AS link
                JOIN characters AS character ON character.id = link.character_id
                WHERE link.media_id = $1::BIGINT
                  AND character.workspace_id = $2::BIGINT
                LIMIT 1
                """,
                int(media_id),
                scoped_workspace_id,
            )
            if not linked:
                raise ValueError("Материал не принадлежит выбранному пространству.")

            existing = await connection.fetchrow(
                """
                SELECT status, source
                FROM media_rework_items
                WHERE workspace_id = $1::BIGINT
                  AND media_id = $2::BIGINT
                FOR UPDATE
                """,
                scoped_workspace_id,
                int(media_id),
            )
            await connection.execute(
                """
                UPDATE character_media AS link
                SET is_public = FALSE
                WHERE link.media_id = $1::BIGINT
                  AND EXISTS (
                        SELECT 1
                        FROM characters AS character
                        WHERE character.id = link.character_id
                          AND character.workspace_id = $2::BIGINT
                      )
                """,
                int(media_id),
                scoped_workspace_id,
            )
            if (
                existing is not None
                and str(existing["status"]) in _ACTIVE_STATUSES
                and str(existing["source"]) in {"admin", "mixed"}
            ):
                return False

            if existing is None:
                await connection.execute(
                    """
                    INSERT INTO media_rework_items (
                        workspace_id,
                        media_id,
                        status,
                        source,
                        reason,
                        requested_by,
                        last_action_by,
                        updated_at
                    )
                    VALUES (
                        $1::BIGINT,
                        $2::BIGINT,
                        'needs_fix',
                        'admin',
                        $4::TEXT,
                        $3::BIGINT,
                        $3::BIGINT,
                        NOW()
                    )
                    """,
                    scoped_workspace_id,
                    int(media_id),
                    int(user_id),
                    reason,
                )
            else:
                source = "admin" if str(existing["source"]) == "admin" else "mixed"
                await connection.execute(
                    """
                    UPDATE media_rework_items
                    SET status = 'needs_fix',
                        source = $4::VARCHAR,
                        reason = $5::TEXT,
                        requested_by = $3::BIGINT,
                        last_action_by = $3::BIGINT,
                        resolved_at = NULL,
                        updated_at = NOW()
                    WHERE workspace_id = $1::BIGINT
                      AND media_id = $2::BIGINT
                    """,
                    scoped_workspace_id,
                    int(media_id),
                    int(user_id),
                    source,
                    reason,
                )

            await connection.execute(
                """
                INSERT INTO media_rework_events (
                    workspace_id,
                    media_id,
                    action,
                    source,
                    actor_user_id,
                    reason
                )
                VALUES (
                    $1::BIGINT,
                    $2::BIGINT,
                    'admin_flagged',
                    'admin',
                    $3::BIGINT,
                    $4::TEXT
                )
                """,
                scoped_workspace_id,
                int(media_id),
                int(user_id),
                reason,
            )
    return True


__all__ = ("request_manual_rework",)
