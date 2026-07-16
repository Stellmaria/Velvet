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


__all__ = (
    "MediaFileCheckTarget",
    "MediaQualityRunResult",
    "MediaScanTarget",
    "StoredFingerprint",
)
