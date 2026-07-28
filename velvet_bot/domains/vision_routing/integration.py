from __future__ import annotations

import json
from typing import Any

from velvet_bot.ai_vision import profile_to_semantic_text
from velvet_bot.database import Database
from velvet_bot.domains.vision_routing.models import VisionCascadeResult
from velvet_bot.domains.vision_routing.service import VisionCascadeRouter
from velvet_bot.resilient_ai_vision import (
    ResilientMediaAIRepository,
    ResilientMediaAIVisionService,
)


class RoutedVisionProfile(dict[str, Any]):
    def __init__(self, result: VisionCascadeResult) -> None:
        super().__init__(result.profile)
        self.route = result.route.value
        self.provider = result.provider
        self.model = result.model
        self.cache_hit = result.cache_hit
        self.content_hash = result.content_hash


class VisionCascadeAdapter:
    """Structural VisionClient adapter for the existing semantic worker."""

    def __init__(self, router: VisionCascadeRouter) -> None:
        self._router = router
        self.provider = router.provider
        self.model = router.model
        self.base_url = "cascade"

    async def health(self) -> bool:
        return await self._router.health()

    async def analyze(self, source: bytes) -> RoutedVisionProfile:
        result = await self._router.analyze(source)
        return RoutedVisionProfile(result)


class CascadeMediaAIRepository(ResilientMediaAIRepository):
    def __init__(self, database: Database) -> None:
        super().__init__(database)

    async def mark_ready(self, media_id: int, profile: dict[str, Any]) -> None:
        provider = str(getattr(profile, "provider", "") or "").strip() or None
        model = str(getattr(profile, "model", "") or "").strip() or None
        route = str(getattr(profile, "route", "") or "").strip() or None
        cache_hit = bool(getattr(profile, "cache_hit", False))
        content_hash = str(getattr(profile, "content_hash", "") or "").strip() or None
        async with self._database.acquire() as connection:
            await connection.execute(
                """UPDATE media_ai_profiles
                   SET status='ready',analysis=$2::JSONB,semantic_text=$3::TEXT,
                       provider=COALESCE($4::VARCHAR,provider),
                       model=COALESCE($5::VARCHAR,model),
                       error_message=NULL,analyzed_at=NOW(),updated_at=NOW()
                   WHERE media_id=$1::BIGINT""",
                int(media_id),
                json.dumps(dict(profile), ensure_ascii=False),
                profile_to_semantic_text(dict(profile)),
                provider,
                model[:160] if model else None,
            )
            await connection.execute(
                """UPDATE ai_vision_cache
                   SET updated_at=NOW()
                   WHERE content_hash=$1::CHAR(64)
                     AND model=$2::VARCHAR
                     AND $1::TEXT IS NOT NULL""",
                content_hash,
                model,
            )
        if route:
            profile["_velvet_route"] = route
        if cache_hit:
            profile["_velvet_cache_hit"] = True


class CascadeMediaAIVisionService(ResilientMediaAIVisionService):
    pass


__all__ = (
    "CascadeMediaAIRepository",
    "CascadeMediaAIVisionService",
    "RoutedVisionProfile",
    "VisionCascadeAdapter",
)
