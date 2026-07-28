from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Sequence

from velvet_bot.database import Database
from velvet_bot.domains.vision_routing.models import (
    CachedVisionAnalysis,
    VisionCascadeResult,
    VisionRoute,
)


class VisionAnalysisCacheRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def find(
        self,
        *,
        content_hash: str,
        analysis_type: str,
        prompt_version: int,
        models: Sequence[str],
    ) -> CachedVisionAnalysis | None:
        ordered_models = tuple(dict.fromkeys(model.strip() for model in models if model.strip()))
        if not ordered_models:
            return None
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """SELECT id,content_hash,analysis_type,prompt_version,route,
                              provider,model,result,confidence,input_tokens,
                              output_tokens,actual_cost_rub
                       FROM ai_vision_cache
                       WHERE content_hash=$1::CHAR(64)
                         AND analysis_type=$2::VARCHAR
                         AND prompt_version=$3::INTEGER
                         AND model=ANY($4::VARCHAR[])
                       ORDER BY array_position($4::VARCHAR[],model),updated_at DESC
                       FOR UPDATE
                       LIMIT 1""",
                    content_hash,
                    analysis_type.strip(),
                    int(prompt_version),
                    list(ordered_models),
                )
                if row is None:
                    return None
                await connection.execute(
                    """UPDATE ai_vision_cache
                       SET hit_count=hit_count+1,last_hit_at=NOW(),updated_at=NOW()
                       WHERE id=$1::BIGINT""",
                    int(row["id"]),
                )
        result = row["result"]
        profile = dict(result) if isinstance(result, dict) else {}
        return CachedVisionAnalysis(
            cache_id=int(row["id"]),
            content_hash=str(row["content_hash"]).strip(),
            analysis_type=str(row["analysis_type"]),
            prompt_version=int(row["prompt_version"]),
            route=VisionRoute(str(row["route"])),
            provider=str(row["provider"]),
            model=str(row["model"]),
            profile=profile,
            confidence=int(row["confidence"] or 0),
            input_tokens=int(row["input_tokens"] or 0),
            output_tokens=int(row["output_tokens"] or 0),
            actual_cost_rub=Decimal(row["actual_cost_rub"] or 0),
        )

    async def store(
        self,
        result: VisionCascadeResult,
        *,
        analysis_type: str,
        prompt_version: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        actual_cost_rub: Decimal = Decimal("0"),
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """INSERT INTO ai_vision_cache(
                       content_hash,analysis_type,prompt_version,route,provider,model,
                       result,confidence,input_tokens,output_tokens,actual_cost_rub)
                   VALUES(
                       $1::CHAR(64),$2::VARCHAR,$3::INTEGER,$4::VARCHAR,$5::VARCHAR,
                       $6::VARCHAR,$7::JSONB,$8::SMALLINT,$9::BIGINT,$10::BIGINT,
                       $11::NUMERIC)
                   ON CONFLICT (content_hash,analysis_type,model,prompt_version)
                   DO UPDATE SET
                       route=EXCLUDED.route,
                       provider=EXCLUDED.provider,
                       result=EXCLUDED.result,
                       confidence=EXCLUDED.confidence,
                       input_tokens=EXCLUDED.input_tokens,
                       output_tokens=EXCLUDED.output_tokens,
                       actual_cost_rub=EXCLUDED.actual_cost_rub,
                       updated_at=NOW()""",
                result.content_hash,
                analysis_type.strip(),
                int(prompt_version),
                result.route.value,
                result.provider.strip(),
                result.model.strip(),
                json.dumps(dict(result.profile), ensure_ascii=False, default=str),
                max(0, min(int(result.confidence), 100)),
                max(0, int(input_tokens)),
                max(0, int(output_tokens)),
                actual_cost_rub,
            )

    async def stats(self) -> dict[str, Any]:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT COUNT(*) AS entries,COALESCE(SUM(hit_count),0) AS hits,
                          COALESCE(SUM(actual_cost_rub),0) AS stored_cost_rub
                   FROM ai_vision_cache"""
            )
        return {
            "entries": int(row["entries"] or 0),
            "hits": int(row["hits"] or 0),
            "stored_cost_rub": Decimal(row["stored_cost_rub"] or 0),
        }


__all__ = ("VisionAnalysisCacheRepository",)
