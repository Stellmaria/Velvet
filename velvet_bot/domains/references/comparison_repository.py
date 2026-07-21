from __future__ import annotations

import json

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


async def _save_report(
    database: Database,
    *,
    character_id: int,
    reference_id: int,
    result_file_id: str,
    result_file_unique_id: str | None,
    provider: str,
    model: str,
    report: dict[str, object],
    created_by: int | None,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> int:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            INSERT INTO reference_comparison_reports (
                workspace_id, character_id, reference_id,
                result_file_id, result_file_unique_id,
                provider, model, overall_score, face_score, hair_score, body_score,
                unique_traits_score, confidence, verdict, report, created_by
            )
            VALUES (
                $1::BIGINT, $2::BIGINT, $3::BIGINT, $4::TEXT, $5::TEXT,
                $6::VARCHAR, $7::VARCHAR, $8::SMALLINT, $9::SMALLINT,
                $10::SMALLINT, $11::SMALLINT, $12::SMALLINT, $13::SMALLINT,
                $14::VARCHAR, $15::JSONB, $16::BIGINT
            )
            RETURNING id
            """,
            int(workspace_id),
            int(character_id),
            int(reference_id),
            result_file_id,
            result_file_unique_id,
            provider[:64],
            model[:160],
            int(report["overall_score"]),
            int(report["face_score"]),
            int(report["hair_score"]),
            int(report["body_score"]),
            int(report["unique_traits_score"]),
            int(report["confidence"]),
            str(report["verdict"]),
            json.dumps(report, ensure_ascii=False),
            created_by,
        )
    return int(value)


__all__ = ("_save_report",)
