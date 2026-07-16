from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PreviewRecord:
    file_id: str | None
    file_unique_id: str | None
    width: int | None
    height: int | None
    source: str | None
    source_chat_id: int | None
    source_message_id: int | None
    archive_chat_id: int | None
    archive_message_id: int | None


@dataclass(frozen=True, slots=True)
class PreviewPayload:
    file_id: str
    file_unique_id: str | None
    width: int | None
    height: int | None
    source: str


__all__ = ("PreviewPayload", "PreviewRecord")
