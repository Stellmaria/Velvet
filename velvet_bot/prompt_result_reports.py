from __future__ import annotations

import json
from typing import Any

from velvet_bot.database import Database


class PromptResultReportRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def save(
        self,
        *,
        result_file_id: str,
        result_file_unique_id: str | None,
        prompt_text: str,
        provider: str,
        model: str,
        report: dict[str, Any],
        created_by: int | None,
    ) -> int:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO prompt_result_comparison_reports (
                    result_file_id,
                    result_file_unique_id,
                    prompt_text,
                    provider,
                    model,
                    analysis_version,
                    overall_score,
                    subject_score,
                    composition_score,
                    lighting_score,
                    palette_score,
                    environment_score,
                    style_score,
                    technical_score,
                    confidence,
                    verdict,
                    report,
                    created_by
                )
                VALUES (
                    $1::TEXT, $2::TEXT, $3::TEXT, $4::VARCHAR, $5::VARCHAR,
                    1, $6::SMALLINT, $7::SMALLINT, $8::SMALLINT,
                    $9::SMALLINT, $10::SMALLINT, $11::SMALLINT,
                    $12::SMALLINT, $13::SMALLINT, $14::SMALLINT,
                    $15::VARCHAR, $16::JSONB, $17::BIGINT
                )
                RETURNING id
                """,
                result_file_id,
                result_file_unique_id,
                prompt_text,
                provider[:64],
                model[:160],
                int(report["overall_score"]),
                int(report["subject_score"]),
                int(report["composition_score"]),
                int(report["lighting_score"]),
                int(report["palette_score"]),
                int(report["environment_score"]),
                int(report["style_score"]),
                int(report["technical_score"]),
                int(report["confidence"]),
                str(report["verdict"]),
                json.dumps(report, ensure_ascii=False),
                created_by,
            )
        return int(value)


__all__ = ("PromptResultReportRepository",)
