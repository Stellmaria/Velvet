from __future__ import annotations

import json
from typing import Any

from velvet_bot.database import Database
from velvet_bot.velvet_formatting import FormattingMode


class VelvetFormattingReportRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def save(
        self,
        *,
        mode: FormattingMode,
        source_text: str,
        provider: str,
        model: str,
        payload: dict[str, Any],
        rendered_text: str,
        created_by: int | None,
    ) -> int:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO velvet_formatting_reports (
                    mode,
                    source_text,
                    provider,
                    model,
                    analysis_version,
                    payload,
                    rendered_text,
                    created_by
                )
                VALUES (
                    $1::VARCHAR, $2::TEXT, $3::VARCHAR, $4::VARCHAR, 1,
                    $5::JSONB, $6::TEXT, $7::BIGINT
                )
                RETURNING id
                """,
                mode,
                source_text,
                provider[:64],
                model[:160],
                json.dumps(payload, ensure_ascii=False),
                rendered_text,
                created_by,
            )
        return int(value)


__all__ = ("VelvetFormattingReportRepository",)
