from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.visual_fingerprint import VisualFingerprint


@dataclass(frozen=True, slots=True)
class MediaScanTarget:
    media_id: int
    telegram_file_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class StoredFingerprint:
    media_id: int
    fingerprint: VisualFingerprint


@dataclass(frozen=True, slots=True)
class MediaFileCheckTarget:
    media_id: int
    telegram_file_id: str


@dataclass(frozen=True, slots=True)
class MediaQualityRunResult:
    fingerprint_targets: int
    file_checks: int


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    id: int
    first_media_id: int
    second_media_id: int
    similarity_score: int
    phash_distance: int
    center_distance: int
    dhash_distance: int
    ahash_distance: int
    exact_bytes: bool
    status: str
    first_file_name: str
    second_file_name: str
    first_file_id: str
    second_file_id: str
    first_media_type: str
    second_media_type: str
    first_mime_type: str | None
    second_mime_type: str | None
    first_characters: tuple[str, ...]
    second_characters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DuplicatePage:
    items: tuple[DuplicateCandidate, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


__all__ = (
    "DuplicateCandidate",
    "DuplicatePage",
    "MediaFileCheckTarget",
    "MediaQualityRunResult",
    "MediaScanTarget",
    "StoredFingerprint",
)
