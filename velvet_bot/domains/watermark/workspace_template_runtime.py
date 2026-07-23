from __future__ import annotations

from typing import Any

from velvet_bot.domains.watermark.models import WatermarkSettings, WatermarkWorkItem
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.watermark_templates import (
    WorkspaceWatermarkTemplateRepository,
)


_applied = False
_original_create_job = WatermarkService.create_job


async def _create_job_with_workspace_template(
    self: WatermarkService,
    *,
    owner_user_id: int,
    chat_id: int,
    source_message_id: int,
    source_file_id: str,
    source_file_unique_id: str | None,
    source_path: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    logo_kind: str = "builtin",
    logo_path: str | None = None,
    logo_width: float | None = None,
    logo_height: float | None = None,
    logo_name: str | None = None,
) -> WatermarkWorkItem:
    repository = self._repository  # type: ignore[attr-defined]
    settings = WatermarkSettings()
    database = getattr(repository, "_database", None)
    if int(workspace_id) != DEFAULT_WORKSPACE_ID and database is not None:
        settings = await WorkspaceWatermarkTemplateRepository(database).get(workspace_id)
    return await repository.create_job(
        owner_user_id=owner_user_id,
        chat_id=chat_id,
        source_message_id=source_message_id,
        source_file_id=source_file_id,
        source_file_unique_id=source_file_unique_id,
        source_path=source_path,
        settings=settings,
        workspace_id=workspace_id,
        logo_kind=logo_kind,
        logo_path=logo_path,
        logo_width=logo_width,
        logo_height=logo_height,
        logo_name=logo_name,
    )


def install_workspace_watermark_templates() -> None:
    global _applied
    if _applied:
        return
    _applied = True
    WatermarkService.create_job = _create_job_with_workspace_template  # type: ignore[method-assign]


__all__ = ("install_workspace_watermark_templates",)
