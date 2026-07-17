from __future__ import annotations

import json
from typing import Any

from velvet_bot.database import Database
from velvet_bot.palette_composition_analysis import PaletteMetrics


class PaletteCompositionReportRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def save(
        self,
        *,
        result_file_id: str,
        result_file_unique_id: str | None,
        provider: str,
        model: str,
        metrics: PaletteMetrics,
        report: dict[str, Any],
        created_by: int | None,
    ) -> int:
        async with self._database._require_pool().acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO palette_composition_reports (
                    result_file_id,
                    result_file_unique_id,
                    provider,
                    model,
                    analysis_version,
                    width,
                    height,
                    palette,
                    composition_score,
                    balance_score,
                    framing_score,
                    hierarchy_score,
                    depth_score,
                    lighting_score,
                    palette_harmony_score,
                    confidence,
                    verdict,
                    report,
                    created_by
                )
                VALUES (
                    $1::TEXT, $2::TEXT, $3::VARCHAR, $4::VARCHAR, 1,
                    $5::INTEGER, $6::INTEGER, $7::JSONB,
                    $8::SMALLINT, $9::SMALLINT, $10::SMALLINT,
                    $11::SMALLINT, $12::SMALLINT, $13::SMALLINT,
                    $14::SMALLINT, $15::SMALLINT, $16::VARCHAR,
                    $17::JSONB, $18::BIGINT
                )
                RETURNING id
                """,
                result_file_id,
                result_file_unique_id,
                provider[:64],
                model[:160],
                metrics.width,
                metrics.height,
                json.dumps(metrics.as_dict(), ensure_ascii=False),
                int(report["composition_score"]),
                int(report["balance_score"]),
                int(report["framing_score"]),
                int(report["hierarchy_score"]),
                int(report["depth_score"]),
                int(report["lighting_score"]),
                int(report["palette_harmony_score"]),
                int(report["confidence"]),
                str(report["verdict"]),
                json.dumps(report, ensure_ascii=False),
                created_by,
            )
        return int(value)


__all__ = ("PaletteCompositionReportRepository",)
