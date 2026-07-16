from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from statistics import median

from PIL import Image, ImageOps, UnidentifiedImageError

FINGERPRINT_VERSION = 1


class VisualFingerprintError(ValueError):
    """Raised when an image cannot be decoded for visual comparison."""


@dataclass(frozen=True, slots=True)
class VisualFingerprint:
    content_sha256: str
    phash: str
    center_phash: str
    dhash: str
    ahash: str
    width: int
    height: int
    image_format: str | None
    version: int = FINGERPRINT_VERSION


@dataclass(frozen=True, slots=True)
class FingerprintComparison:
    similarity_score: int
    phash_distance: int
    center_distance: int
    dhash_distance: int
    ahash_distance: int
    exact_bytes: bool

    @property
    def is_candidate(self) -> bool:
        if self.exact_bytes:
            return True
        if self.phash_distance <= 7:
            return True
        return (
            self.phash_distance <= 10
            and self.dhash_distance <= 10
            and self.ahash_distance <= 12
        )


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image.copy()
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        result = background.convert("RGB")
        rgba.close()
        background.close()
        return result
    return image.convert("RGB")


def _bits_to_hex(bits: list[bool]) -> str:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    width = max(1, math.ceil(len(bits) / 4))
    return f"{value:0{width}x}"


def _average_hash(gray: Image.Image) -> str:
    resized = gray.resize((8, 8), Image.Resampling.LANCZOS)
    values = list(resized.getdata())
    resized.close()
    average = sum(values) / len(values)
    return _bits_to_hex([value >= average for value in values])


def _difference_hash(gray: Image.Image) -> str:
    resized = gray.resize((9, 8), Image.Resampling.LANCZOS)
    values = list(resized.getdata())
    resized.close()
    bits: list[bool] = []
    for row in range(8):
        start = row * 9
        for column in range(8):
            bits.append(values[start + column] > values[start + column + 1])
    return _bits_to_hex(bits)


def _phash(gray: Image.Image) -> str:
    size = 32
    low = 8
    resized = gray.resize((size, size), Image.Resampling.LANCZOS)
    pixels = list(resized.getdata())
    resized.close()

    cos_table = [
        [math.cos((2 * position + 1) * frequency * math.pi / (2 * size))
         for position in range(size)]
        for frequency in range(low)
    ]
    values: list[float] = []
    for vertical_frequency in range(low):
        vertical_cos = cos_table[vertical_frequency]
        for horizontal_frequency in range(low):
            horizontal_cos = cos_table[horizontal_frequency]
            coefficient = 0.0
            for y in range(size):
                row_offset = y * size
                vertical_weight = vertical_cos[y]
                row_sum = 0.0
                for x in range(size):
                    row_sum += pixels[row_offset + x] * horizontal_cos[x]
                coefficient += vertical_weight * row_sum
            values.append(coefficient)

    threshold = median(values[1:])
    return _bits_to_hex([value >= threshold for value in values])


def _center_crop(image: Image.Image, ratio: float = 0.84) -> Image.Image:
    width, height = image.size
    crop_width = max(1, round(width * ratio))
    crop_height = max(1, round(height * ratio))
    left = max(0, (width - crop_width) // 2)
    top = max(0, (height - crop_height) // 2)
    return image.crop((left, top, left + crop_width, top + crop_height))


def build_visual_fingerprint(source: bytes) -> VisualFingerprint:
    if not source:
        raise VisualFingerprintError("Telegram вернул пустой файл.")
    try:
        with Image.open(io.BytesIO(source)) as opened:
            if getattr(opened, "is_animated", False):
                opened.seek(0)
            image_format = opened.format
            transposed = ImageOps.exif_transpose(opened)
            transposed.load()
            image = _flatten_to_rgb(transposed)
            if transposed is not opened:
                transposed.close()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise VisualFingerprintError("Файл не удалось прочитать как изображение.") from error

    try:
        width, height = image.size
        if width <= 0 or height <= 0:
            raise VisualFingerprintError("У изображения некорректный размер.")
        gray = image.convert("L")
        center = _center_crop(gray)
        try:
            return VisualFingerprint(
                content_sha256=hashlib.sha256(source).hexdigest(),
                phash=_phash(gray),
                center_phash=_phash(center),
                dhash=_difference_hash(gray),
                ahash=_average_hash(gray),
                width=width,
                height=height,
                image_format=image_format,
            )
        finally:
            gray.close()
            center.close()
    finally:
        image.close()


def hamming_distance(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()


def compare_fingerprints(
    first: VisualFingerprint,
    second: VisualFingerprint,
) -> FingerprintComparison:
    direct_phash = hamming_distance(first.phash, second.phash)
    cross_distances = (
        direct_phash,
        hamming_distance(first.phash, second.center_phash),
        hamming_distance(first.center_phash, second.phash),
        hamming_distance(first.center_phash, second.center_phash),
    )
    phash_distance = min(cross_distances)
    center_distance = hamming_distance(first.center_phash, second.center_phash)
    dhash_distance = hamming_distance(first.dhash, second.dhash)
    ahash_distance = hamming_distance(first.ahash, second.ahash)
    exact_bytes = first.content_sha256 == second.content_sha256
    if exact_bytes:
        score = 100
    else:
        penalty = (
            phash_distance * 1.7
            + dhash_distance * 0.85
            + ahash_distance * 0.45
        )
        score = max(0, min(99, round(100 - penalty)))
    return FingerprintComparison(
        similarity_score=score,
        phash_distance=phash_distance,
        center_distance=center_distance,
        dhash_distance=dhash_distance,
        ahash_distance=ahash_distance,
        exact_bytes=exact_bytes,
    )
