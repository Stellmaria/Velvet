from __future__ import annotations

import asyncio
import io
import math
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile
from PIL import Image, ImageOps, UnidentifiedImageError

from velvet_bot.archive_catalog import ArchivedMedia

# Cloud Bot API limits. Images that already satisfy sendPhoto requirements are
# uploaded byte-for-byte. Conversion is used only when Telegram cannot accept
# the original payload as a photo, never to create a small viewer thumbnail.
BOT_API_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024
TELEGRAM_PHOTO_MAX_BYTES = 10 * 1024 * 1024
TELEGRAM_PHOTO_TARGET_BYTES = TELEGRAM_PHOTO_MAX_BYTES - 128 * 1024
TELEGRAM_PHOTO_MAX_DIMENSION_SUM = 10_000
TELEGRAM_PHOTO_MAX_ASPECT_RATIO = 20.0

# Compatibility names kept for older imports and tests.
PREVIEW_MAX_BYTES = TELEGRAM_PHOTO_TARGET_BYTES
PREVIEW_MAX_EDGE = TELEGRAM_PHOTO_MAX_DIMENSION_SUM
PREVIEW_MAX_ASPECT_RATIO = TELEGRAM_PHOTO_MAX_ASPECT_RATIO


class ImagePreviewError(ValueError):
    """Raised when an image document cannot be displayed as a Telegram photo."""


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        rgba.close()
        return background.convert("RGB")
    return image.convert("RGB")


def _pad_extreme_aspect_ratio(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ImagePreviewError("У изображения некорректный размер.")

    ratio = max(width / height, height / width)
    if ratio <= TELEGRAM_PHOTO_MAX_ASPECT_RATIO:
        return image

    if width > height:
        canvas_size = (width, math.ceil(width / TELEGRAM_PHOTO_MAX_ASPECT_RATIO))
    else:
        canvas_size = (math.ceil(height / TELEGRAM_PHOTO_MAX_ASPECT_RATIO), height)

    canvas = Image.new("RGB", canvas_size, (255, 255, 255))
    left = (canvas_size[0] - width) // 2
    top = (canvas_size[1] - height) // 2
    canvas.paste(image, (left, top))
    return canvas


def _fit_telegram_geometry(image: Image.Image) -> Image.Image:
    width, height = image.size
    dimension_sum = width + height
    if dimension_sum <= TELEGRAM_PHOTO_MAX_DIMENSION_SUM:
        return image

    scale = TELEGRAM_PHOTO_MAX_DIMENSION_SUM / dimension_sum
    return image.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.Resampling.LANCZOS,
    )


def _geometry_is_supported(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        return False
    ratio = max(width / height, height / width)
    return (
        width + height <= TELEGRAM_PHOTO_MAX_DIMENSION_SUM
        and ratio <= TELEGRAM_PHOTO_MAX_ASPECT_RATIO
    )


def _encode_jpeg_under_limit(image: Image.Image) -> bytes:
    current = image
    qualities = (98, 96, 94, 92, 90, 88, 85, 82, 78, 74, 70)

    for _ in range(8):
        for quality in qualities:
            output = io.BytesIO()
            current.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
                subsampling=0,
            )
            payload = output.getvalue()
            if len(payload) <= TELEGRAM_PHOTO_TARGET_BYTES:
                return payload

        width, height = current.size
        if width <= 1200 and height <= 1200:
            break
        resized = current.resize(
            (max(1, round(width * 0.94)), max(1, round(height * 0.94))),
            Image.Resampling.LANCZOS,
        )
        if current is not image:
            current.close()
        current = resized

    if current is not image:
        current.close()
    raise ImagePreviewError(
        "Изображение не удалось подготовить под лимит Telegram без сильной потери качества."
    )


def _safe_stem(source_name: str) -> str:
    stem = Path(source_name or "image").stem.strip() or "image"
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in stem
    )[:80]


def _original_filename(source_name: str, image_format: str | None) -> str:
    suffix = Path(source_name or "").suffix.casefold()
    if suffix in {".jpg", ".jpeg", ".png"}:
        return Path(source_name).name
    extension = ".png" if image_format == "PNG" else ".jpg"
    return f"{_safe_stem(source_name)}{extension}"


def render_photo_preview(
    source: bytes,
    source_name: str,
) -> tuple[bytes, str]:
    """Prepare a full-quality Telegram photo from an archived image document.

    Original JPEG and PNG bytes are preserved whenever they already satisfy
    sendPhoto limits. Otherwise the complete image is converted only as much as
    Telegram requires; no 2560 px thumbnail or 4.5 MB preview is produced.
    """
    if not source:
        raise ImagePreviewError("Telegram вернул пустой файл.")
    if len(source) > BOT_API_DOWNLOAD_MAX_BYTES:
        raise ImagePreviewError(
            "Изображение больше 20 МБ нельзя скачать через облачный Bot API."
        )

    try:
        with Image.open(io.BytesIO(source)) as opened:
            image_format = opened.format
            width, height = opened.size
            is_animated = bool(getattr(opened, "is_animated", False))

            if (
                len(source) <= TELEGRAM_PHOTO_MAX_BYTES
                and image_format in {"JPEG", "PNG"}
                and not is_animated
                and _geometry_is_supported(width, height)
            ):
                return source, _original_filename(source_name, image_format)

            if is_animated:
                opened.seek(0)
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ImagePreviewError("Файл не удалось прочитать как изображение.") from error

    try:
        rgb = _flatten_to_rgb(image)
        if rgb is not image:
            image.close()
        image = rgb

        padded = _pad_extreme_aspect_ratio(image)
        if padded is not image:
            image.close()
        image = padded

        fitted = _fit_telegram_geometry(image)
        if fitted is not image:
            image.close()
        image = fitted

        payload = _encode_jpeg_under_limit(image)
    finally:
        image.close()

    return payload, f"{_safe_stem(source_name)}_telegram.jpg"


async def build_image_document_preview(
    bot: Bot,
    media: ArchivedMedia,
) -> BufferedInputFile:
    """Download an image document and return a full-quality photo upload."""
    if media.file_size is not None and media.file_size > BOT_API_DOWNLOAD_MAX_BYTES:
        raise ImagePreviewError(
            "Изображение больше 20 МБ нельзя показать фотографией через облачный Bot API."
        )

    destination = io.BytesIO()
    await bot.download(
        media.telegram_file_id,
        destination=destination,
        seek=True,
    )
    payload, filename = await asyncio.to_thread(
        render_photo_preview,
        destination.getvalue(),
        media.display_file_name,
    )
    return BufferedInputFile(payload, filename=filename)
