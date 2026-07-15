from __future__ import annotations

import asyncio
import io
import math
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile
from PIL import Image, ImageOps, UnidentifiedImageError

from velvet_bot.archive_catalog import ArchivedMedia

# Telegram displays photos reliably when they stay comfortably below its hard
# upload and geometry limits. The original document remains untouched in the
# archive; only this temporary viewer copy is compressed.
PREVIEW_MAX_EDGE = 2560
PREVIEW_MAX_BYTES = 4_500_000
PREVIEW_MAX_ASPECT_RATIO = 20.0


class ImagePreviewError(ValueError):
    """Raised when an image document cannot be converted into a photo preview."""


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image.convert("RGB")


def _pad_extreme_aspect_ratio(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ImagePreviewError("У изображения некорректный размер.")

    ratio = max(width / height, height / width)
    if ratio <= PREVIEW_MAX_ASPECT_RATIO:
        return image

    if width > height:
        canvas_size = (width, math.ceil(width / PREVIEW_MAX_ASPECT_RATIO))
    else:
        canvas_size = (math.ceil(height / PREVIEW_MAX_ASPECT_RATIO), height)

    canvas = Image.new("RGB", canvas_size, (255, 255, 255))
    left = (canvas_size[0] - width) // 2
    top = (canvas_size[1] - height) // 2
    canvas.paste(image, (left, top))
    return canvas


def _encode_jpeg_under_limit(image: Image.Image) -> bytes:
    current = image
    qualities = (90, 84, 78, 72, 66, 60)

    for _ in range(5):
        for quality in qualities:
            output = io.BytesIO()
            current.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
                subsampling="4:2:0",
            )
            payload = output.getvalue()
            if len(payload) <= PREVIEW_MAX_BYTES:
                return payload

        width, height = current.size
        if width <= 640 and height <= 640:
            break
        resized = current.resize(
            (max(1, int(width * 0.82)), max(1, int(height * 0.82))),
            Image.Resampling.LANCZOS,
        )
        if resized is not current:
            current.close()
        current = resized

    raise ImagePreviewError("Не удалось подготовить превью допустимого размера.")


def render_photo_preview(
    source: bytes,
    source_name: str,
) -> tuple[bytes, str]:
    """Convert an image document into a Telegram-friendly JPEG photo preview."""
    if not source:
        raise ImagePreviewError("Telegram вернул пустой файл.")

    try:
        with Image.open(io.BytesIO(source)) as opened:
            # Animated image documents are represented by their first frame in
            # the archive viewer. The original animation remains downloadable.
            if getattr(opened, "is_animated", False):
                opened.seek(0)
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ImagePreviewError("Файл не удалось прочитать как изображение.") from error

    try:
        image.thumbnail(
            (PREVIEW_MAX_EDGE, PREVIEW_MAX_EDGE),
            Image.Resampling.LANCZOS,
        )
        rgb = _flatten_to_rgb(image)
        if rgb is not image:
            image.close()
        image = _pad_extreme_aspect_ratio(rgb)
        if image is not rgb:
            rgb.close()
        payload = _encode_jpeg_under_limit(image)
    finally:
        image.close()

    stem = Path(source_name or "image").stem.strip() or "image"
    safe_stem = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in stem
    )[:80]
    return payload, f"{safe_stem}_preview.jpg"


async def build_image_document_preview(
    bot: Bot,
    media: ArchivedMedia,
) -> BufferedInputFile:
    """Download the original Telegram document and build a compressed photo copy."""
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
