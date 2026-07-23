from __future__ import annotations

from dataclasses import replace

from velvet_bot.database import Database
from velvet_bot.domains.watermark.models import WatermarkSettings


class WorkspaceWatermarkTemplateRepository:
    """Persistent default settings for new watermark jobs in one workspace."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get(self, workspace_id: int) -> WatermarkSettings:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT position, color, opacity, size, margin, lock_layer
                FROM workspace_watermark_templates
                WHERE workspace_id = $1::BIGINT
                """,
                int(workspace_id),
            )
        if row is None:
            return WatermarkSettings()
        return WatermarkSettings(
            position=str(row["position"]),
            color=str(row["color"]),
            opacity=int(row["opacity"]),
            size=float(row["size"]),
            margin=float(row["margin"]),
            enabled=True,
            lock=bool(row["lock_layer"]),
        ).normalized()

    async def save(
        self,
        *,
        workspace_id: int,
        settings: WatermarkSettings,
        updated_by_user_id: int,
    ) -> WatermarkSettings:
        normalized = settings.normalized()
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO workspace_watermark_templates (
                    workspace_id, position, color, opacity, size, margin,
                    lock_layer, updated_by_user_id
                )
                VALUES (
                    $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::INTEGER,
                    $5::DOUBLE PRECISION, $6::DOUBLE PRECISION,
                    $7::BOOLEAN, $8::BIGINT
                )
                ON CONFLICT (workspace_id) DO UPDATE
                SET position = EXCLUDED.position,
                    color = EXCLUDED.color,
                    opacity = EXCLUDED.opacity,
                    size = EXCLUDED.size,
                    margin = EXCLUDED.margin,
                    lock_layer = EXCLUDED.lock_layer,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = NOW()
                """,
                int(workspace_id),
                normalized.position,
                normalized.color,
                normalized.opacity,
                normalized.size,
                normalized.margin,
                normalized.lock,
                int(updated_by_user_id),
            )
        return normalized

    async def revise(
        self,
        *,
        workspace_id: int,
        updated_by_user_id: int,
        position: str | None = None,
        color: str | None = None,
        opacity_delta: int = 0,
        size_delta: float = 0.0,
        margin_delta: float = 0.0,
        lock: bool | None = None,
    ) -> WatermarkSettings:
        current = await self.get(workspace_id)
        updated = replace(
            current,
            position=position if position is not None else current.position,
            color=color if color is not None else current.color,
            opacity=current.opacity + int(opacity_delta),
            size=current.size + float(size_delta),
            margin=current.margin + float(margin_delta),
            lock=current.lock if lock is None else bool(lock),
        ).normalized()
        return await self.save(
            workspace_id=workspace_id,
            settings=updated,
            updated_by_user_id=updated_by_user_id,
        )

    async def reset(self, workspace_id: int) -> WatermarkSettings:
        async with self._database.acquire() as connection:
            await connection.execute(
                "DELETE FROM workspace_watermark_templates WHERE workspace_id = $1::BIGINT",
                int(workspace_id),
            )
        return WatermarkSettings()


__all__ = ("WorkspaceWatermarkTemplateRepository",)
