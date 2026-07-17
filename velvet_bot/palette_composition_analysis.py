from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import urllib.request
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageOps, ImageStat, UnidentifiedImageError

from velvet_bot.ai_vision import (
    VisionAnalysisError,
    VisionClient,
    _extract_json_object,
    _prepare_image,
)

_SCORE_FIELDS = (
    "composition_score",
    "balance_score",
    "framing_score",
    "hierarchy_score",
    "depth_score",
    "lighting_score",
    "palette_harmony_score",
    "confidence",
)
_LIST_FIELDS = ("strengths", "issues", "recommendations")
_TEXT_FIELDS = (
    "summary_ru",
    "focal_point_ru",
    "subject_placement_ru",
    "crop_assessment_ru",
    "negative_space_ru",
    "visual_flow_ru",
    "depth_summary_ru",
    "lighting_summary_ru",
    "palette_summary_ru",
)

_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        **{field: {"type": "integer"} for field in _SCORE_FIELDS},
        "verdict": {
            "type": "string",
            "enum": ["strong", "review", "weak", "insufficient"],
        },
        "composition_pattern": {
            "type": "string",
            "enum": [
                "centered",
                "rule_of_thirds",
                "diagonal",
                "symmetrical",
                "triangular",
                "layered",
                "closeup",
                "mixed",
                "unclear",
            ],
        },
        "lighting_direction": {
            "type": "string",
            "enum": ["front", "side", "back", "top", "bottom", "mixed", "unclear"],
        },
        "lighting_quality": {
            "type": "string",
            "enum": ["soft", "hard", "mixed", "unclear"],
        },
        "crop_risk": {
            "type": "string",
            "enum": ["low", "medium", "high", "unclear"],
        },
        **{field: {"type": "string"} for field in _TEXT_FIELDS},
        **{
            field: {"type": "array", "items": {"type": "string"}}
            for field in _LIST_FIELDS
        },
    },
    "required": [
        *_SCORE_FIELDS,
        "verdict",
        "composition_pattern",
        "lighting_direction",
        "lighting_quality",
        "crop_risk",
        *_TEXT_FIELDS,
        *_LIST_FIELDS,
    ],
    "additionalProperties": False,
}

_ANALYSIS_PROMPT = """
Ты выполняешь профессиональный визуальный разбор одного художественного изображения
для редакции Velvet Anatomy. Изображение может содержать взрослых персонажей и
художественную обнажённость. Не оценивай допустимость сюжета и не определяй личность.
Анализируй только видимые художественные и технические признаки.

Проверь:
- главный фокус и визуальную иерархию;
- баланс масс, симметрию, правило третей, диагонали и направление взгляда;
- положение персонажей и предметов внутри кадра;
- обрезания тела, лица, рук и важных объектов;
- негативное пространство и риск неудачного кадрирования при публикации;
- передний, средний и задний план, глубину и разделение объекта с фоном;
- направление, жёсткость и согласованность света;
- гармонию фактической палитры, контраст акцентов и цветовую температуру.

Фактическая палитра извлечена программно и будет передана ниже. Не выдумывай другие
HEX-коды. Используй её как измеренные данные, а изображение — для понимания ролей
цветов и композиции.

issues включают только конкретные видимые проблемы. recommendations должны быть
практическими: что сместить, обрезать, осветлить, затемнить, приглушить или усилить.
Не советуй абстрактно «сделать красивее». Все тексты пиши по-русски, кратко и
предметно. Верни только JSON.
""".strip()


@dataclass(frozen=True, slots=True)
class PaletteColor:
    hex_code: str
    red: int
    green: int
    blue: int
    share: float
    luminance: int
    role: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "hex": self.hex_code,
            "rgb": [self.red, self.green, self.blue],
            "share": self.share,
            "luminance": self.luminance,
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class PaletteMetrics:
    width: int
    height: int
    aspect_ratio: float
    brightness: int
    contrast: int
    saturation: int
    temperature: str
    colors: tuple[PaletteColor, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "temperature": self.temperature,
            "colors": [color.as_dict() for color in self.colors],
        }


def _score(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(parsed, 100))


def _text(value: Any, *, limit: int = 900) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _strings(value: Any, *, limit: int = 8, length: int = 320) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item, limit=length)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _enum(value: Any, allowed: set[str], fallback: str) -> str:
    cleaned = str(value or "").strip().casefold()
    return cleaned if cleaned in allowed else fallback


def _rgb_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(first, second)))


def _temperature_label(red: float, blue: float) -> str:
    difference = red - blue
    if difference >= 12:
        return "warm"
    if difference <= -12:
        return "cool"
    return "neutral"


def extract_palette_metrics(source: bytes, *, color_count: int = 6) -> PaletteMetrics:
    try:
        with Image.open(io.BytesIO(source)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = image.size
            working = image.copy()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise VisionAnalysisError("Файл не удалось прочитать как изображение.") from error

    try:
        working.thumbnail((640, 640), Image.Resampling.LANCZOS)
        stat = ImageStat.Stat(working)
        mean_red, mean_green, mean_blue = stat.mean[:3]
        brightness_raw = (
            0.2126 * mean_red + 0.7152 * mean_green + 0.0722 * mean_blue
        )
        contrast_raw = sum(stat.stddev[:3]) / 3
        hsv = working.convert("HSV")
        saturation_raw = ImageStat.Stat(hsv).mean[1]

        quantized = working.quantize(
            colors=max(8, min(color_count * 2, 16)),
            method=Image.Quantize.MEDIANCUT,
        )
        palette = quantized.getpalette() or []
        counts = quantized.getcolors(maxcolors=256) or []
        total = max(1, sum(count for count, _ in counts))
        candidates: list[tuple[int, tuple[int, int, int]]] = []
        for count, index in sorted(counts, reverse=True):
            offset = int(index) * 3
            if offset + 2 >= len(palette):
                continue
            rgb = tuple(int(value) for value in palette[offset : offset + 3])
            candidates.append((int(count), rgb))

        selected: list[tuple[int, tuple[int, int, int]]] = []
        for count, rgb in candidates:
            if selected and any(_rgb_distance(rgb, other) < 24 for _, other in selected):
                continue
            selected.append((count, rgb))
            if len(selected) >= max(3, min(color_count, 8)):
                break
        if not selected and candidates:
            selected = candidates[: max(1, color_count)]

        colors: list[PaletteColor] = []
        for position, (count, rgb) in enumerate(selected):
            red, green, blue = rgb
            luminance = round(
                (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 2.55
            )
            share = round((count / total) * 100, 1)
            if position == 0:
                role = "dominant"
            elif position <= 2:
                role = "secondary"
            else:
                role = "accent"
            colors.append(
                PaletteColor(
                    hex_code=f"#{red:02X}{green:02X}{blue:02X}",
                    red=red,
                    green=green,
                    blue=blue,
                    share=share,
                    luminance=max(0, min(luminance, 100)),
                    role=role,
                )
            )

        return PaletteMetrics(
            width=width,
            height=height,
            aspect_ratio=round(width / max(1, height), 3),
            brightness=max(0, min(round(brightness_raw / 2.55), 100)),
            contrast=max(0, min(round(contrast_raw / 1.1), 100)),
            saturation=max(0, min(round(saturation_raw / 2.55), 100)),
            temperature=_temperature_label(mean_red, mean_blue),
            colors=tuple(colors),
        )
    finally:
        working.close()


def build_palette_card(metrics: PaletteMetrics) -> bytes:
    colors = metrics.colors or (
        PaletteColor("#808080", 128, 128, 128, 100.0, 50, "dominant"),
    )
    width = 960
    height = 260
    card = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(card)
    swatch_top = 32
    swatch_bottom = 185
    swatch_width = width / len(colors)
    for index, color in enumerate(colors):
        left = round(index * swatch_width)
        right = round((index + 1) * swatch_width)
        draw.rectangle(
            (left, swatch_top, right, swatch_bottom),
            fill=(color.red, color.green, color.blue),
        )
        label = f"{color.hex_code}  {color.share:.1f}%"
        text_x = left + 8
        text_y = swatch_bottom + 12
        draw.text((text_x, text_y), label, fill="black")
    footer = (
        f"brightness {metrics.brightness}/100   contrast {metrics.contrast}/100   "
        f"saturation {metrics.saturation}/100   temperature {metrics.temperature}"
    )
    draw.text((12, 232), footer, fill="black")
    output = io.BytesIO()
    card.save(output, format="PNG", optimize=True)
    card.close()
    return output.getvalue()


def normalize_composition_report(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VisionAnalysisError("Qwen вернул разбор композиции не в виде JSON-объекта.")

    scores = {field: _score(payload.get(field)) for field in _SCORE_FIELDS}
    texts = {field: _text(payload.get(field)) for field in _TEXT_FIELDS}
    lists = {field: _strings(payload.get(field)) for field in _LIST_FIELDS}

    pattern = _enum(
        payload.get("composition_pattern"),
        {
            "centered",
            "rule_of_thirds",
            "diagonal",
            "symmetrical",
            "triangular",
            "layered",
            "closeup",
            "mixed",
            "unclear",
        },
        "unclear",
    )
    lighting_direction = _enum(
        payload.get("lighting_direction"),
        {"front", "side", "back", "top", "bottom", "mixed", "unclear"},
        "unclear",
    )
    lighting_quality = _enum(
        payload.get("lighting_quality"),
        {"soft", "hard", "mixed", "unclear"},
        "unclear",
    )
    crop_risk = _enum(
        payload.get("crop_risk"),
        {"low", "medium", "high", "unclear"},
        "unclear",
    )

    if scores["confidence"] < 30:
        verdict = "insufficient"
    elif scores["composition_score"] >= 82 and not lists["issues"]:
        verdict = "strong"
    elif scores["composition_score"] >= 55:
        verdict = "review"
    else:
        verdict = "weak"

    if not texts["summary_ru"]:
        texts["summary_ru"] = {
            "strong": "Композиция читается уверенно и не содержит явных проблем.",
            "review": "Композиция рабочая, но отдельные решения требуют проверки.",
            "weak": "Композиционные проблемы заметно ослабляют изображение.",
            "insufficient": "Изображение не позволяет выполнить надёжный разбор.",
        }[verdict]

    return {
        **scores,
        "verdict": verdict,
        "composition_pattern": pattern,
        "lighting_direction": lighting_direction,
        "lighting_quality": lighting_quality,
        "crop_risk": crop_risk,
        **texts,
        **lists,
    }


class CompositionAnalysisClient(VisionClient):
    def _prompt(self, metrics: PaletteMetrics) -> str:
        measured = json.dumps(metrics.as_dict(), ensure_ascii=False, separators=(",", ":"))
        return (
            _ANALYSIS_PROMPT
            + "\n\nИзмеренные данные изображения:\n"
            + measured
            + "\n\nВерни один JSON-объект по этой JSON Schema без markdown и текста вне JSON:\n"
            + json.dumps(_ANALYSIS_SCHEMA, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _parse_ollama_payload(payload: dict[str, Any]) -> dict[str, Any]:
        message = payload.get("message")
        message = message if isinstance(message, dict) else {}
        candidates = (
            message.get("content"),
            message.get("thinking"),
            payload.get("response"),
        )
        errors: list[str] = []
        for value in candidates:
            text = str(value or "").strip()
            if not text:
                continue
            try:
                return normalize_composition_report(_extract_json_object(text))
            except VisionAnalysisError as error:
                errors.append(str(error))
        diagnostic = (
            f"content={len(str(message.get('content') or ''))}, "
            f"thinking={len(str(message.get('thinking') or ''))}, "
            f"done_reason={payload.get('done_reason')!r}, "
            f"eval_count={payload.get('eval_count')!r}"
        )
        if errors:
            diagnostic += "; " + "; ".join(errors)
        raise VisionAnalysisError(
            f"Qwen не вернул пригодный разбор композиции ({diagnostic})."
        )

    async def analyze_composition(
        self,
        source: bytes,
        metrics: PaletteMetrics,
    ) -> dict[str, Any]:
        prepared = await asyncio.to_thread(_prepare_image, source)
        image = base64.b64encode(prepared).decode("ascii")
        prompt = self._prompt(metrics)

        if self.provider == "ollama":
            diagnostics: list[str] = []
            for use_schema in (True, False):
                body = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image],
                        }
                    ],
                    "format": _ANALYSIS_SCHEMA if use_schema else "json",
                    "stream": False,
                    "think": False,
                    "keep_alive": "15m",
                    "options": {"temperature": 0, "num_predict": 2800},
                }
                request = urllib.request.Request(
                    f"{self.base_url}/api/chat",
                    data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    headers=self._headers(),
                    method="POST",
                )
                payload = await asyncio.to_thread(
                    self._read_json,
                    request,
                    timeout=self.timeout_seconds,
                )
                try:
                    return self._parse_ollama_payload(payload)
                except VisionAnalysisError as error:
                    diagnostics.append(
                        f"{'schema' if use_schema else 'json'}: {error}"
                    )
            raise VisionAnalysisError(
                "Qwen не вернул разбор композиции после двух режимов Ollama. "
                + " | ".join(diagnostics)
            )

        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image}"},
                        },
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 2800,
        }
        request = urllib.request.Request(
            f"{root}/v1/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        payload = await asyncio.to_thread(
            self._read_json,
            request,
            timeout=self.timeout_seconds,
        )
        choices = payload.get("choices") or []
        response_text = (
            ((choices[0] or {}).get("message") or {}).get("content")
            if choices
            else ""
        )
        return normalize_composition_report(
            _extract_json_object(str(response_text or ""))
        )


__all__ = (
    "CompositionAnalysisClient",
    "PaletteColor",
    "PaletteMetrics",
    "build_palette_card",
    "extract_palette_metrics",
    "normalize_composition_report",
)
