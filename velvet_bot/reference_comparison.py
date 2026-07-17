from __future__ import annotations

import asyncio
import base64
import json
import urllib.request
from dataclasses import dataclass
from typing import Any

from velvet_bot.ai_vision import (
    VisionAnalysisError,
    VisionClient,
    _extract_json_object,
    _prepare_image,
)

_LIST_FIELDS = (
    "face_matches",
    "face_differences",
    "hair_matches",
    "hair_differences",
    "body_matches",
    "body_differences",
    "unique_matches",
    "unique_differences",
    "uncertain_areas",
)
_SCORE_FIELDS = (
    "overall_score",
    "face_score",
    "hair_score",
    "body_score",
    "unique_traits_score",
    "confidence",
)
_VISIBILITY_FIELDS = (
    "reference_face",
    "result_face",
    "reference_body",
    "result_body",
    "reference_unique_traits",
    "result_unique_traits",
)

_COMPARISON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer"},
        "face_score": {"type": "integer"},
        "hair_score": {"type": "integer"},
        "body_score": {"type": "integer"},
        "unique_traits_score": {"type": "integer"},
        "confidence": {"type": "integer"},
        "verdict": {
            "type": "string",
            "enum": ["strong", "partial", "weak", "insufficient"],
        },
        "summary_ru": {"type": "string"},
        "face_matches": {"type": "array", "items": {"type": "string"}},
        "face_differences": {"type": "array", "items": {"type": "string"}},
        "hair_matches": {"type": "array", "items": {"type": "string"}},
        "hair_differences": {"type": "array", "items": {"type": "string"}},
        "body_matches": {"type": "array", "items": {"type": "string"}},
        "body_differences": {"type": "array", "items": {"type": "string"}},
        "unique_matches": {"type": "array", "items": {"type": "string"}},
        "unique_differences": {"type": "array", "items": {"type": "string"}},
        "uncertain_areas": {"type": "array", "items": {"type": "string"}},
        "visibility": {
            "type": "object",
            "properties": {
                key: {"type": "integer"} for key in _VISIBILITY_FIELDS
            },
            "required": list(_VISIBILITY_FIELDS),
            "additionalProperties": False,
        },
    },
    "required": [
        *_SCORE_FIELDS,
        "verdict",
        "summary_ru",
        *_LIST_FIELDS,
        "visibility",
    ],
    "additionalProperties": False,
}

_COMPARISON_PROMPT = """
Перед тобой два изображения одного заявленного персонажа.

ИЗОБРАЖЕНИЕ 1 — эталонный референс внешности.
ИЗОБРАЖЕНИЕ 2 — результат генерации, который нужно проверить.

Сравнивай только видимые внешние признаки. Это не распознавание личности и не поиск
реального человека. Не называй человека, не делай выводов о происхождении, здоровье,
характере или других чувствительных свойствах.

Проверь соответствие результата референсу по четырём блокам:

1. ЛИЦО: форма и пропорции лица, глаза, брови, нос, губы, скулы, подбородок,
линия челюсти, форма головы и видимая растительность на лице.
2. ВОЛОСЫ: цвет, длина, структура, линия роста, причёска и видимые особенности.
3. ТЕЛОСЛОЖЕНИЕ: общий силуэт, ширина плеч, пропорции торса, талии, рук и ног,
мышечность или полнота. Не сравнивай то, что скрыто одеждой, позой или кадрированием.
4. УНИКАЛЬНЫЕ ПРИЗНАКИ: только реально видимые татуировки, шрамы, родинки,
пирсинг и другие устойчивые детали. Не придумывай скрытые признаки.

Не штрафуй результат за другой фон, стиль, одежду, позу, выражение лица, свет или
ракурс сами по себе. Учитывай их только если они мешают надёжно увидеть внешность.
Если лицо или тело недостаточно видны хотя бы на одном изображении, снижай
visibility и прямо указывай, что сравнение соответствующего блока ненадёжно.

Оценки 0–100 означают визуальное соответствие видимых признаков, а не вероятность
того, что это один и тот же реальный человек. Все пояснения пиши по-русски, коротко,
предметно и без категоричных утверждений там, где деталей недостаточно.
""".strip()


def _score(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(parsed, 100))


def _strings(value: Any, *, limit: int = 8, length: int = 260) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = " ".join(str(item or "").split()).strip()[:length]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def normalize_reference_comparison(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VisionAnalysisError("Qwen вернул сравнение не в виде JSON-объекта.")

    scores = {field: _score(payload.get(field)) for field in _SCORE_FIELDS}
    visibility_raw = payload.get("visibility")
    visibility_raw = visibility_raw if isinstance(visibility_raw, dict) else {}
    visibility = {
        field: _score(visibility_raw.get(field)) for field in _VISIBILITY_FIELDS
    }

    lists = {field: _strings(payload.get(field)) for field in _LIST_FIELDS}
    summary = " ".join(str(payload.get("summary_ru") or "").split()).strip()[:900]

    face_visibility = min(visibility["reference_face"], visibility["result_face"])
    body_visibility = min(visibility["reference_body"], visibility["result_body"])
    unique_visibility = min(
        visibility["reference_unique_traits"],
        visibility["result_unique_traits"],
    )

    if face_visibility < 35 and body_visibility < 35:
        verdict = "insufficient"
    elif scores["overall_score"] >= 82 and scores["confidence"] >= 55:
        verdict = "strong"
    elif scores["overall_score"] >= 58:
        verdict = "partial"
    else:
        verdict = "weak"

    if body_visibility < 35 and not any(
        "телослож" in item.casefold() or "тело" in item.casefold()
        for item in lists["uncertain_areas"]
    ):
        lists["uncertain_areas"].append(
            "Телосложение недостаточно видно хотя бы на одном изображении."
        )
    if unique_visibility < 25 and not any(
        "уникаль" in item.casefold() or "тату" in item.casefold()
        for item in lists["uncertain_areas"]
    ):
        lists["uncertain_areas"].append(
            "Уникальные признаки недостаточно видны для надёжного сравнения."
        )

    if not summary:
        summary = {
            "strong": "Видимые признаки результата в основном соответствуют референсу.",
            "partial": "Есть заметные совпадения, но часть внешности отличается или видна не полностью.",
            "weak": "Обнаружены существенные расхождения видимых внешних признаков.",
            "insufficient": "Деталей недостаточно для надёжного сравнения внешности.",
        }[verdict]

    return {
        **scores,
        "verdict": verdict,
        "summary_ru": summary,
        **lists,
        "visibility": visibility,
    }


@dataclass(frozen=True, slots=True)
class ReferenceComparisonResult:
    character_id: int
    character_name: str
    reference_id: int
    reference_index: int
    report: dict[str, Any]


class ReferenceComparisonClient(VisionClient):
    def _prompt(self) -> str:
        return (
            _COMPARISON_PROMPT
            + "\n\nВерни только один JSON-объект по этой JSON Schema без markdown и "
            + "текста вне JSON:\n"
            + json.dumps(_COMPARISON_SCHEMA, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _parse_payload(payload: dict[str, Any]) -> dict[str, Any]:
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
                return normalize_reference_comparison(_extract_json_object(text))
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
            f"Qwen не вернул пригодное сравнение внешности ({diagnostic})."
        )

    async def compare(self, reference: bytes, result: bytes) -> dict[str, Any]:
        prepared_reference, prepared_result = await asyncio.gather(
            asyncio.to_thread(_prepare_image, reference),
            asyncio.to_thread(_prepare_image, result),
        )
        images = [
            base64.b64encode(prepared_reference).decode("ascii"),
            base64.b64encode(prepared_result).decode("ascii"),
        ]
        prompt = self._prompt()

        if self.provider == "ollama":
            diagnostics: list[str] = []
            for use_schema in (True, False):
                body = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": images,
                        }
                    ],
                    "format": _COMPARISON_SCHEMA if use_schema else "json",
                    "stream": False,
                    "think": False,
                    "keep_alive": "15m",
                    "options": {"temperature": 0, "num_predict": 2200},
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
                    return self._parse_payload(payload)
                except VisionAnalysisError as error:
                    diagnostics.append(
                        f"{'schema' if use_schema else 'json'}: {error}"
                    )
            raise VisionAnalysisError(
                "Qwen не вернул сравнение после двух режимов Ollama. "
                + " | ".join(diagnostics)
            )

        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image}"},
                }
            )
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 2200,
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
        return normalize_reference_comparison(
            _extract_json_object(str(response_text or ""))
        )


__all__ = (
    "ReferenceComparisonClient",
    "ReferenceComparisonResult",
    "normalize_reference_comparison",
)
