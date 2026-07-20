from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IEND_CHUNK = b"\x00\x00\x00\x00IEND\xaeB`\x82"
_PADDING_PREFIX = b"VelvetPadding\x00"


@dataclass(frozen=True, slots=True)
class ArchiveWatermarkOutput:
    path: Path
    width: int
    height: int
    source_bytes: int
    output_bytes: int


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    if len(chunk_type) != 4:
        raise ValueError("PNG chunk type must contain four bytes.")
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", checksum)
    )


def _pad_png_to_size(path: Path, minimum_bytes: int) -> None:
    data = path.read_bytes()
    if len(data) >= minimum_bytes:
        return
    if not data.startswith(_PNG_SIGNATURE) or not data.endswith(_IEND_CHUNK):
        raise ValueError("Krita output должен быть корректным PNG.")

    missing = minimum_bytes - len(data)
    payload_size = max(len(_PADDING_PREFIX), missing - 12)
    payload = _PADDING_PREFIX + (b"0" * (payload_size - len(_PADDING_PREFIX)))
    padded = data[:-len(_IEND_CHUNK)] + _png_chunk(b"tEXt", payload) + _IEND_CHUNK
    path.write_bytes(padded)


def prepare_archive_watermark_output(
    source_path: str | Path,
    output_path: str | Path,
) -> ArchiveWatermarkOutput:
    """Validate unchanged pixels and keep the output byte size at least the source size."""
    source = Path(source_path)
    output = Path(output_path)
    if not source.is_file():
        raise ValueError("Исходный файл watermark не найден.")
    if not output.is_file():
        raise ValueError("Финальный PNG watermark не найден.")

    with Image.open(source) as source_image:
        source_image.load()
        source_size = source_image.size
    with Image.open(output) as output_image:
        output_image.load()
        output_size = output_image.size
        output_format = str(output_image.format or "").upper()

    if output_size != source_size:
        raise ValueError(
            "Krita изменила размеры изображения: "
            f"{source_size[0]}×{source_size[1]} → {output_size[0]}×{output_size[1]}."
        )
    if output_format != "PNG":
        raise ValueError("Финальный файл публичного архива должен быть PNG без потерь.")

    source_bytes = source.stat().st_size
    _pad_png_to_size(output, source_bytes)

    with Image.open(output) as verified:
        verified.load()
        if verified.size != source_size:
            raise ValueError("PNG повреждён после сохранения размера файла.")

    return ArchiveWatermarkOutput(
        path=output,
        width=source_size[0],
        height=source_size[1],
        source_bytes=source_bytes,
        output_bytes=output.stat().st_size,
    )


__all__ = ("ArchiveWatermarkOutput", "prepare_archive_watermark_output")
