from __future__ import annotations

from aiogram.types import PhotoSize

from velvet_bot.domains.references import ReferenceMediaPayload


def reference_payload_from_photo(photo: PhotoSize) -> ReferenceMediaPayload:
    return ReferenceMediaPayload(
        telegram_file_id=photo.file_id,
        telegram_file_unique_id=photo.file_unique_id,
    )


__all__ = ("reference_payload_from_photo",)
