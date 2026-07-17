from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import urllib.request
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from velvet_bot.ai_vision import (
    VisionAnalysisError,
    VisionClient,
    _extract_json_object,
)

_ANALYSIS_VERSION = 1
_SCORE_FIELDS = (
    "overall_score",
    "style_score",
    "lighting_score",
    "palette_score",
    "environment_score",
    "composition_score",
    "narrative_score",
    "character_continuity_score",
    "technical_score",
    "confidence",
)
_LIST_FIELDS = ("shared_traits", "set_issues", "uncertain_areas")
_ITEM_STATUSES = {"core", "outlier", "uncertain"}

_SET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        **{field: {"type": "integer"} for field in _SCORE_FIELDS},
        "verdict": {
            "type": "string",
            "enum": ["coherent", "review", "incoherent", "insufficient"],
        },
        "summary_ru": {"type": "string"},
        "shared_traits": {"type": "array", "items": {"type": "string"}},
        "set_issues": {"type": "array", "items": {"type": "string"}},
        "uncertain_areas": {"type": "array", "items": {"type": "string"}},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "consistency_score": {"type": "integer"},
                    "status": {
                        "type": "string",
                        "enum": ["core", "outlier", "uncertain"],
                    },
                    "reasons": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["index", "consistency_score", "status", "reasons"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        *_SCORE_FIELDS,
        "verdict",
        "summary_ru",
        *_LIST_FIELDS,
        "items",
    ],
    "additionalProperties": False,
}

_SET_PROMPT = """
Перед тобой один контакт-лист из нескольких подписанных кадров одного заявленного
медиасета Velvet. Под каждым кадром указан его номер. Оцени не красоту отдельных
работ, а то, воспринимаются ли они как единая художественная серия.

Проверь следующие блоки:
1. Общий визуальный стиль и уровень реалистичности.
2. Логику освещения, контраста и экспозиции между кадрами.
3. Согласованность палитры и цветокоррекции.
4. Связность локации, окружения, эпохи, предметов и художественной темы.
5. Совместимость композиции, масштаба планов и ракурсов внутри серии.
6. Нарративную связность: ощущается ли развитие одной сцены или общей идеи.
7. Стабильность одного и того же персонажа только там, где в описании кадров
   повторяется одинаковое имя. Разные персонажи внутри общего тематического сета
   допустимы и не являются ошибкой.
8. Техническую согласованность: резкость, детализация, артефакты, водяные знаки,
   интерфейс и резкие скачки качества.

Кадр считается outlier, только если он заметно разрушает единство серии. Другой
ракурс, поза, выражение лица или крупность плана сами по себе не являются причиной
исключения. Если деталей недостаточно, используй uncertain, а не выдумывай дефект.

Это не распознавание личности. Не называй реальных людей и не делай выводов о
происхождении, здоровье, возрасте, характере или других чувствительных свойствах.
На изображениях могут быть взрослые персонажи и художественная обнажённость:
оценивай её только как нейтральную часть композиции и не морализируй.

Все пояснения пиши по-русски, кратко и предметно. Верни ровно по одному элементу
items для каждого кадра контакт-листа.
""".strip()


@dataclass(frozen=True, slots=True)
class SetConsistencyInput:
    media_id: int
    image: bytes
    characters: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContactSheetResult:
    image: bytes
    width: int
    height: int


def _score(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(parsed, 100))


def _strings(value: Any, *, limit: int = 10, length: int = 280) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for raw in value:
        text = " ".join(str(raw or "").split()).strip()[:length]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _open_rgb(source: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(source)) as opened:
            transposed = ImageOps.exif_transpose(opened)
            transposed.load()
            return transposed.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise VisionAnalysisError("Один из файлов сета не удалось прочитать как изображение.") from error


def build_contact_sheet(items: tuple[SetConsistencyInput, ...]) -> ContactSheetResult:
    if not 2 <= len(items) <= 12:
        raise VisionAnalysisError("Для проверки сета нужно от 2 до 12 изображений.")

    columns = 2 if len(items) <= 4 else 3 if len(items) <= 9 else 4
    tile_width = 320
    image_height = 320
    label_height = 38
    rows = math.ceil(len(items) / columns)
    sheet = Image.new(
        "RGB",
        (columns * tile_width, rows * (image_height + label_height)),
        (24, 24, 24),
    )
    draw = ImageDraw.Draw(sheet)

    try:
        for index, item in enumerate(items, start=1):
            image = _open_rgb(item.image)
            try:
                fitted = ImageOps.contain(
                    image,
                    (tile_width - 16, image_height - 16),
                    method=Image.Resampling.LANCZOS,
                )
                column = (index - 1) % columns
                row = (index - 1) // columns
                x0 = column * tile_width
                y0 = row * (image_height + label_height)
                x = x0 + (tile_width - fitted.width) // 2
                y = y0 + (image_height - fitted.height) // 2
                sheet.paste(fitted, (x, y))
                fitted.close()
                draw.rectangle(
                    (x0, y0 + image_height, x0 + tile_width, y0 + image_height + label_height),
                    fill=(12, 12, 12),
                )
                draw.text(
                    (x0 + 10, y0 + image_height + 11),
                    f"Frame {index} | media #{item.media_id}",
                    fill=(245, 245, 245),
                )
            finally:
                image.close()

        output = io.BytesIO()
        sheet.save(output, format="JPEG", quality=88, optimize=True)
        return ContactSheetResult(
            image=output.getvalue(),
            width=sheet.width,
            height=sheet.height,
        )
    finally:
        sheet.close()


def normalize_set_consistency(
    payload: Any,
    media_ids: tuple[int, ...],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VisionAnalysisError("Qwen вернул проверку сета не в виде JSON-объекта.")
    if not 2 <= len(media_ids) <= 12:
        raise VisionAnalysisError("Неверное количество материалов для проверки сета.")

    scores = {field: _score(payload.get(field)) for field in _SCORE_FIELDS}
    lists = {field: _strings(payload.get(field)) for field in _LIST_FIELDS}
    summary = " ".join(str(payload.get("summary_ru") or "").split()).strip()[:1000]

    raw_items = payload.get("items")
    raw_items = raw_items if isinstance(raw_items, list) else []
    by_index: dict[int, dict[str, Any]] = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        try:
            index = int(raw.get("index"))
        except (TypeError, ValueError):
            continue
        if index < 1 or index > len(media_ids) or index in by_index:
            continue
        status = str(raw.get("status") or "uncertain").strip().casefold()
        if status not in _ITEM_STATUSES:
            status = "uncertain"
        item_score = _score(raw.get("consistency_score"))
        if item_score < 50 and status == "core":
            status = "outlier"
        by_index[index] = {
            "index": index,
            "media_id": media_ids[index - 1],
            "consistency_score": item_score,
            "status": status,
            "reasons": _strings(raw.get("reasons"), limit=6),
        }

    normalized_items: list[dict[str, Any]] = []
    for index, media_id in enumerate(media_ids, start=1):
        normalized_items.append(
            by_index.get(
                index,
                {
                    "index": index,
                    "media_id": media_id,
                    "consistency_score": 0,
                    "status": "uncertain",
                    "reasons": ["Qwen не вернул отдельную оценку этого кадра."],
                },
            )
        )

    outlier_count = sum(item["status"] == "outlier" for item in normalized_items)
    uncertain_count = sum(item["status"] == "uncertain" for item in normalized_items)
    incoherent_threshold = max(2, math.ceil(len(media_ids) * 0.35))

    if scores["confidence"] < 35 or uncertain_count >= math.ceil(len(media_ids) / 2):
        verdict = "insufficient"
    elif scores["overall_score"] < 55 or outlier_count >= incoherent_threshold:
        verdict = "incoherent"
    elif outlier_count or lists["set_issues"] or scores["overall_score"] < 78:
        verdict = "review"
    else:
        verdict = "coherent"

    if not summary:
        summary = {
            "coherent": "Кадры воспринимаются как единая художественная серия.",
            "review": "Сет в основном связан, но отдельные кадры требуют ручной проверки.",
            "incoherent": "Несколько кадров заметно нарушают целостность серии.",
            "insufficient": "Деталей недостаточно для надёжной оценки целостности сета.",
        }[verdict]

    return {
        **scores,
        "verdict": verdict,
        "summary_ru": summary,
        **lists,
        "items": normalized_items,
        "analysis_version": _ANALYSIS_VERSION,
    }


class SetConsistencyClient(VisionClient):
    def _prompt(self, items: tuple[SetConsistencyInput, ...]) -> str:
        mapping: list[str] = []
        repeated: dict[str, int] = {}
        for index, item in enumerate(items, start=1):
            names = tuple(name.strip() for name in item.characters if name.strip())
            for name in set(names):
                repeated[name.casefold()] = repeated.get(name.casefold(), 0) + 1
            mapping.append(
                f"Кадр {index} = media #{item.media_id}; персонажи: "
                + (", ".join(names) if names else "не указаны")
            )
        repeated_names = sorted(name for name, count in repeated.items() if count > 1)
        continuity_note = (
            "Повторяющиеся персонажи, для которых нужно проверить стабильность: "
            + ", ".join(repeated_names)
            if repeated_names
            else (
                "Одинаковые имена персонажей между кадрами не повторяются. "
                "Не снижай character_continuity_score из-за разных персонажей; "
                "используй нейтральную оценку 100."
            )
        )
        return (
            _SET_PROMPT
            + "\n\nСООТВЕТСТВИЕ ПОДПИСЕЙ:\n"
            + "\n".join(mapping)
            + "\n\n"
            + continuity_note
            + "\n\nВерни только один JSON-объект по этой JSON Schema без markdown "
            + "и пояснений вне JSON:\n"
            + json.dumps(_SET_SCHEMA, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _parse_payload(payload: dict[str, Any], media_ids: tuple[int, ...]) -> dict[str, Any]:
        message = payload.get("message")
        message = message if isinstance(message, dict) else {}
        choices = payload.get("choices")
        choice_content = ""
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            first_message = first.get("message")
            if isinstance(first_message, dict):
                choice_content = str(first_message.get("content") or "")
        candidates = (
            message.get("content"),
            message.get("thinking"),
            payload.get("response"),
            choice_content,
        )
        errors: list[str] = []
        for value in candidates:
            text = str(value or "").strip()
            if not text:
                continue
            try:
                return normalize_set_consistency(_extract_json_object(text), media_ids)
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
            f"Qwen не вернул пригодную проверку целостности сета ({diagnostic})."
        )

    async def analyze_set(self, items: tuple[SetConsistencyInput, ...]) -> dict[str, Any]:
        sheet = await asyncio.to_thread(build_contact_sheet, items)
        image_base64 = base64.b64encode(sheet.image).decode("ascii")
        prompt = self._prompt(items)
        media_ids = tuple(item.media_id for item in items)

        if self.provider == "ollama":
            diagnostics: list[str] = []
            for use_schema in (True, False):
                body = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_base64],
                        }
                    ],
                    "format": _SET_SCHEMA if use_schema else "json",
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
                    return self._parse_payload(payload, media_ids)
                except VisionAnalysisError as error:
                    diagnostics.append(
                        f"{'schema' if use_schema else 'json'}: {error}"
                    )
            raise VisionAnalysisError(
                "Qwen не вернул проверку сета после двух режимов Ollama. "
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
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
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
        return self._parse_payload(payload, media_ids)


__all__ = (
    "ContactSheetResult",
    "SetConsistencyClient",
    "SetConsistencyInput",
    "build_contact_sheet",
    "normalize_set_consistency",
)
