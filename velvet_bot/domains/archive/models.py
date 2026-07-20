from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from velvet_bot.domains.characters.models import CharacterRecord


@dataclass(frozen=True, slots=True)
class ArchivedMedia:
    id: int
    telegram_file_id: str
    media_type: str
    original_file_name: str | None
    storage_file_name: str
    mime_type: str | None
    file_size: int | None
    linked_at: datetime
    prompt_post_url: str | None = None
    archive_message_id: int | None = None
    is_spoiler: bool = False
    is_public: bool = True
    requires_adult_channel: bool = False
    media_set_id: int | None = None
    media_set_title: str | None = None
    source_telegram_file_id: str | None = None
    watermark_applied: bool = False
    watermark_approved: bool = False

    @property
    def display_file_name(self) -> str:
        return self.original_file_name or self.storage_file_name

    @property
    def is_image_document(self) -> bool:
        return self.media_type == "document" and (self.mime_type or "").startswith(
            "image/"
        )

    @property
    def belongs_to_set(self) -> bool:
        return self.media_set_id is not None

    @property
    def original_download_file_id(self) -> str:
        return self.source_telegram_file_id or self.telegram_file_id

    @property
    def public_download_file_id(self) -> str | None:
        if self.watermark_applied and self.watermark_approved:
            return self.telegram_file_id
        return None


@dataclass(frozen=True, slots=True)
class ArchivePage:
    character: CharacterRecord
    media: ArchivedMedia | None
    offset: int
    total: int


@dataclass(frozen=True, slots=True)
class DeletedArchiveItem:
    character: CharacterRecord
    media: ArchivedMedia
    remaining_total: int
    orphan_media_removed: bool


__all__ = ("ArchivePage", "ArchivedMedia", "DeletedArchiveItem")
