from __future__ import annotations

import json

from velvet_bot.database import Database


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
) -> int:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            INSERT INTO reference_comparison_reports (
                character_id, reference_id, result_file_id, result_file_unique_id,
                provider, model, overall_score, face_score, hair_score, body_score,
                unique_traits_score, confidence, verdict, report, created_by
            )
            VALUES (
                $1::BIGINT, $2::BIGINT, $3::TEXT, $4::TEXT,
                $5::VARCHAR, $6::VARCHAR, $7::SMALLINT, $8::SMALLINT,
                $9::SMALLINT, $10::SMALLINT, $11::SMALLINT, $12::SMALLINT,
                $13::VARCHAR, $14::JSONB, $15::BIGINT
            )
            RETURNING id
            """,
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
