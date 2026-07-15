from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, Document, Message, PhotoSize

MAX_REFERENCE_DOCUMENT_BYTES = 10 * 1024 * 1024
_SUPPORTED_IMAGE_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }
)
_SUPPORTED_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})

ReferenceSource = PhotoSize | Document


@dataclass(frozen=True, slots=True)
class PreparedReference:
    """Telegram photo identity ready to be stored in character_references."""

    file_id: str
    file_unique_id: str


def validate_reference_document(document: Document) -> str | None:
    """Return a user-facing error when a Telegram document cannot be a photo reference."""
    if (
        document.file_size is not None
        and document.file_size > MAX_REFERENCE_DOCUMENT_BYTES
    ):
        return "Файл слишком большой. Изображение-референс должно быть не больше 10 МБ."

    mime_type = (document.mime_type or "").strip().casefold()
    suffix = Path(document.file_name or "").suffix.casefold()
    if mime_type in _SUPPORTED_IMAGE_MIME_TYPES:
        return None
    if suffix in _SUPPORTED_IMAGE_SUFFIXES:
        return None

    return (
        "Документ должен быть изображением JPG, JPEG, PNG или WEBP. "
        "PDF, архивы и остальные файлы нельзя использовать как референс."
    )


def extract_reference_source(message: Message) -> ReferenceSource | None:
    """Extract the largest photo or a supported image document from a message."""
    if message.photo:
        return message.photo[-1]
    if message.document and validate_reference_document(message.document) is None:
        return message.document
    return None


async def prepare_reference_source(
    source: ReferenceSource,
    *,
    bot: Bot,
    staging_chat_id: int | None,
) -> PreparedReference:
    """Convert an image document into a cached Telegram photo when necessary.

    Telegram document file_ids cannot be passed to sendPhoto or cached-photo inline
    results. The bot therefore uploads the document once as a temporary photo, stores
    the resulting photo file_id and immediately removes the temporary message.
    """
    if isinstance(source, PhotoSize):
        return PreparedReference(
            file_id=source.file_id,
            file_unique_id=source.file_unique_id,
        )

    validation_error = validate_reference_document(source)
    if validation_error is not None:
        raise ValueError(validation_error)
    if staging_chat_id is None:
        raise ValueError(
            "Не настроен LOG_CHAT_ID, поэтому бот не может преобразовать документ "
            "в фотографию. Укажите лог-чат в .env и перезапустите бота."
        )

    buffer = BytesIO()
    await bot.download(source, destination=buffer)
    payload = buffer.getvalue()
    if not payload:
        raise RuntimeError("Telegram вернул пустой файл референса.")

    original_name = Path(source.file_name or "reference.jpg").name
    temporary_message = await bot.send_photo(
        chat_id=staging_chat_id,
        photo=BufferedInputFile(payload, filename=original_name),
        disable_notification=True,
    )
    if not temporary_message.photo:
        raise RuntimeError("Telegram не преобразовал документ в фотографию.")

    prepared = PreparedReference(
        file_id=temporary_message.photo[-1].file_id,
        # Keep the original document unique id so repeated uploads are deduplicated.
        file_unique_id=source.file_unique_id,
    )

    try:
        await bot.delete_message(
            chat_id=staging_chat_id,
            message_id=temporary_message.message_id,
        )
    except TelegramBadRequest:
        # The cached photo file_id remains valid even when cleanup is not permitted.
        pass

    return prepared
