from __future__ import annotations

from velvet_bot.core.config import Settings
from velvet_bot.database import Database
from velvet_bot.domains.roleplay.client import (
    FailoverRoleplayClient,
    RoleplayClient,
    TextRoleplayClient,
)
from velvet_bot.domains.roleplay.service import RoleplayService
from velvet_bot.domains.roleplay.storage import RoleplayRepository


def build_roleplay_service(
    *,
    settings: Settings,
    database: Database,
) -> RoleplayService:
    client: RoleplayClient | None = None
    provider_label = "disabled"
    model_label = "disabled"

    if settings.ai_text_enabled:
        if not settings.ai_text_model:
            raise RuntimeError(
                "AI_TEXT_ENABLED=true требует непустой AI_TEXT_MODEL."
            )
        primary = TextRoleplayClient(
            provider=settings.ai_text_provider,
            base_url=settings.ai_text_base_url,
            model=settings.ai_text_model,
            api_key=settings.ai_text_api_key,
            timeout_seconds=settings.ai_text_timeout_seconds,
            max_output_tokens=settings.ai_text_max_output_tokens,
            max_attempts=settings.ai_text_max_attempts,
        )
        client = primary
        provider_label = settings.ai_text_provider
        model_label = settings.ai_text_model

        if settings.ai_text_fallback_provider and settings.ai_text_fallback_model:
            fallback = TextRoleplayClient(
                provider=settings.ai_text_fallback_provider,
                base_url=settings.ai_text_fallback_base_url,
                model=settings.ai_text_fallback_model,
                api_key=settings.ai_text_fallback_api_key,
                timeout_seconds=settings.ai_text_timeout_seconds,
                max_output_tokens=settings.ai_text_max_output_tokens,
                max_attempts=1,
            )
            client = FailoverRoleplayClient(primary, fallback)
            provider_label = (
                f"{settings.ai_text_provider} -> "
                f"{settings.ai_text_fallback_provider}"
            )
            model_label = (
                f"{settings.ai_text_model} -> "
                f"{settings.ai_text_fallback_model}"
            )

    return RoleplayService(
        repository=RoleplayRepository(database),
        client=client,
        provider_label=provider_label,
        model_label=model_label,
        max_history_messages=settings.ai_text_max_history_messages,
    )


__all__ = ("build_roleplay_service",)
