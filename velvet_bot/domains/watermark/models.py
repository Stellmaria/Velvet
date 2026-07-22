from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import re

_ALLOWED_POSITIONS = frozenset({
    "top_left", "top_center", "top_right",
    "center_left", "center", "center_right",
    "bottom_left", "bottom_center", "bottom_right",
})
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True, slots=True)
class WatermarkSettings:
    position: str = "bottom_right"
    color: str = "auto"
    opacity: int = 70
    size: float = 19.7
    margin: float = 4.4
    enabled: bool = True
    lock: bool = True

    def normalized(self) -> "WatermarkSettings":
        position = self.position.strip().casefold()
        if position not in _ALLOWED_POSITIONS:
            raise ValueError("Неизвестное положение водяного знака.")
        color = self.color.strip().casefold()
        if color != "auto" and not _HEX_COLOR.fullmatch(color):
            raise ValueError("Цвет должен быть auto или HEX вида #D8C8B8.")
        opacity = max(1, min(int(self.opacity), 100))
        size = max(3.0, min(float(self.size), 70.0))
        margin = max(0.0, min(float(self.margin), 30.0))
        return replace(
            self,
            position=position,
            color=color,
            opacity=opacity,
            size=round(size, 1),
            margin=round(margin, 1),
            enabled=bool(self.enabled),
            lock=bool(self.lock),
        )


@dataclass(frozen=True, slots=True)
class WatermarkJob:
    id: int
    owner_user_id: int
    chat_id: int
    source_message_id: int
    source_file_id: str
    source_file_unique_id: str | None
    source_path: str
    status: str
    current_revision: int
    control_message_id: int | None
    preview_message_id: int | None
    final_path: str | None
    created_at: datetime
    updated_at: datetime
    workspace_id: int = 1
    logo_kind: str = "builtin"
    logo_path: str | None = None
    logo_width: float | None = None
    logo_height: float | None = None
    logo_name: str | None = None

    @property
    def archive_media_id(self) -> int | None:
        """Negative source_message_id is reserved for fast archive watermark jobs."""
        return -self.source_message_id if self.source_message_id < 0 else None


@dataclass(frozen=True, slots=True)
class WatermarkRevision:
    job_id: int
    revision: int
    settings: WatermarkSettings
    status: str
    request_path: str | None
    output_path: str | None
    response_path: str | None
    telegram_preview_file_id: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class WatermarkWorkItem:
    job: WatermarkJob
    revision: WatermarkRevision


__all__ = (
    "WatermarkJob",
    "WatermarkRevision",
    "WatermarkSettings",
    "WatermarkWorkItem",
)
