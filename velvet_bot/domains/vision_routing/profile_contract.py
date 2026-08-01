from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from velvet_bot.ai_vision import VisionAnalysisError, normalize_ai_profile
from velvet_bot.domains.vision_routing.models import VisionAnalysisMode

PROFILE_SCHEMA_VERSION = 1

_SEMANTIC_LIST_FIELDS = (
    "themes",
    "genres",
    "settings",
    "eras",
    "environment",
    "objects",
    "wardrobe",
    "composition",
    "lighting",
    "palette",
    "mood",
    "actions",
    "series_keywords",
)
_SEMANTIC_REQUIRED_FIELDS = (
    "series_title_ru",
    "summary_ru",
    *_SEMANTIC_LIST_FIELDS,
    "people_count",
    "confidence",
)
_STRUCTURED_FIELDS = (
    "subjects",
    "composition",
    "pose",
    "camera",
    "body_visibility",
    "covering_method",
    "environment",
    "lighting",
    "visible_text",
    "uncertainties",
    "generation_risks",
)
_STANDARD_CONTENT_MODES = frozenset({"editorial", "other"})
_SENSITIVE_CONTENT_MODES = frozenset(
    {"artistic_nudity", "adult_editorial", "explicit_adult", "other"}
)

_SEMANTIC_PROPERTIES: dict[str, object] = {
    "series_title_ru": {"type": "string"},
    "summary_ru": {"type": "string"},
    **{
        field: {"type": "array", "items": {"type": "string"}}
        for field in _SEMANTIC_LIST_FIELDS
    },
    "people_count": {"type": "integer", "minimum": 0, "maximum": 50},
    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
}
_STRUCTURED_PROPERTIES: dict[str, object] = {
    "subjects": {"type": "array", "items": {"type": "object"}},
    "composition": {"type": "object"},
    "pose": {"type": "object"},
    "camera": {"type": "object"},
    "body_visibility": {"type": "object"},
    "covering_method": {"type": "object"},
    "environment": {"type": "object"},
    "lighting": {"type": "object"},
    "visible_text": {"type": "array", "items": {"type": "string"}},
    "uncertainties": {"type": "array", "items": {"type": "string"}},
    "generation_risks": {"type": "array", "items": {"type": "string"}},
}


def _build_schema(
    *,
    mode: VisionAnalysisMode,
    content_modes: frozenset[str],
) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "integer", "const": PROFILE_SCHEMA_VERSION},
            "prompt_version": {"type": "integer", "minimum": 1},
            "route": {"type": "string", "const": mode.value},
            "content_mode": {"type": "string", "enum": sorted(content_modes)},
            **deepcopy(_SEMANTIC_PROPERTIES),
            "structured": {
                "type": "object",
                "additionalProperties": False,
                "properties": deepcopy(_STRUCTURED_PROPERTIES),
                "required": list(_STRUCTURED_FIELDS),
            },
        },
        "required": [
            "schema_version",
            "prompt_version",
            "route",
            "content_mode",
            *_SEMANTIC_REQUIRED_FIELDS,
            "structured",
        ],
    }


STANDARD_PROFILE_SCHEMA = _build_schema(
    mode=VisionAnalysisMode.STANDARD,
    content_modes=_STANDARD_CONTENT_MODES,
)
SENSITIVE_PROFILE_SCHEMA = _build_schema(
    mode=VisionAnalysisMode.SENSITIVE,
    content_modes=_SENSITIVE_CONTENT_MODES,
)

_STANDARD_PROMPT = """
Проанализируй изображение для тематической группировки художественного архива и
последующего создания точного генеративного промта. Описывай только видимые факты.
Не распознавай личность и не угадывай реального человека, возраст, этничность,
здоровье или другие чувствительные характеристики.

Верни только JSON по предоставленной схеме. Сохрани краткий semantic-блок верхнего
уровня для поиска сетов и подробный structured-блок для композиции, позы, камеры,
света, окружения, видимого текста, неопределённостей и рисков генерации. Не
придумывай скрытые части тела, касания, одежду, предметы или действия. Все
сомнения перечисли в structured.uncertainties. route должен быть standard,
content_mode только editorial либо other.
""".strip()

_SENSITIVE_PROMPT = """
Это разрешённый внутренний анализ изображения после внешнего подтверждения, что
все участники являются взрослыми. Не пытайся определять или угадывать возраст по
внешности и не распознавай личности.

Описывай только действительно видимое. Точно зафиксируй композицию, позу, ракурс,
опоры, касания, перекрытия, способы прикрытия, видимость тела, окружение, свет,
палитру и настроение. Различай artistic_nudity, adult_editorial и explicit_adult,
но не смягчай видимые факты эвфемизмами и не добавляй действий или анатомических
деталей, которых нельзя подтвердить изображением. Скрытые области и неоднозначные
касания перечисли в structured.uncertainties.

Верни только JSON по предоставленной схеме. route должен быть sensitive. Сохрани
краткий semantic-блок верхнего уровня и подробный structured-блок для
Image-to-Prompt и Pose Extractor. Не давай медицинских, возрастных или личностных
заключений.
""".strip()


def prompt_for_mode(mode: VisionAnalysisMode) -> str:
    return _SENSITIVE_PROMPT if mode is VisionAnalysisMode.SENSITIVE else _STANDARD_PROMPT


def schema_for_mode(mode: VisionAnalysisMode) -> Mapping[str, object]:
    return (
        SENSITIVE_PROFILE_SCHEMA
        if mode is VisionAnalysisMode.SENSITIVE
        else STANDARD_PROFILE_SCHEMA
    )


def normalize_routed_profile(
    payload: object,
    *,
    mode: VisionAnalysisMode,
    prompt_version: int,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise VisionAnalysisError("VL-модель вернула не объект JSON.")

    _validate_contract_header(payload, mode=mode, prompt_version=prompt_version)
    _validate_semantic_shape(payload)
    structured_source = _validate_structured_shape(payload)
    semantic = normalize_ai_profile(payload)
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "prompt_version": max(1, int(prompt_version)),
        "route": mode.value,
        "content_mode": str(payload["content_mode"]).strip().casefold(),
        **semantic,
        "structured": {
            "subjects": _bounded_list_of_objects(structured_source["subjects"], limit=8),
            "composition": _bounded_object(structured_source["composition"]),
            "pose": _bounded_object(structured_source["pose"]),
            "camera": _bounded_object(structured_source["camera"]),
            "body_visibility": _bounded_object(structured_source["body_visibility"]),
            "covering_method": _bounded_object(structured_source["covering_method"]),
            "environment": _bounded_object(structured_source["environment"]),
            "lighting": _bounded_object(structured_source["lighting"]),
            "visible_text": _bounded_strings(structured_source["visible_text"], limit=20),
            "uncertainties": _bounded_strings(
                structured_source["uncertainties"],
                limit=20,
            ),
            "generation_risks": _bounded_strings(
                structured_source["generation_risks"],
                limit=20,
            ),
        },
    }


def _validate_contract_header(
    payload: Mapping[str, object],
    *,
    mode: VisionAnalysisMode,
    prompt_version: int,
) -> None:
    if payload.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise VisionAnalysisError("VL schema_version не совпадает с ожидаемой версией.")
    if payload.get("prompt_version") != max(1, int(prompt_version)):
        raise VisionAnalysisError("VL prompt_version не совпадает с запросом.")
    if str(payload.get("route") or "").strip().casefold() != mode.value:
        raise VisionAnalysisError("VL route не совпадает с выбранным режимом.")
    content_mode = str(payload.get("content_mode") or "").strip().casefold()
    allowed = (
        _SENSITIVE_CONTENT_MODES
        if mode is VisionAnalysisMode.SENSITIVE
        else _STANDARD_CONTENT_MODES
    )
    if content_mode not in allowed:
        raise VisionAnalysisError("VL content_mode недопустим для выбранного режима.")


def _validate_semantic_shape(payload: Mapping[str, object]) -> None:
    missing = [field for field in _SEMANTIC_REQUIRED_FIELDS if field not in payload]
    if missing:
        raise VisionAnalysisError(
            "VL semantic profile не содержит обязательные поля: " + ", ".join(missing)
        )
    for field in _SEMANTIC_LIST_FIELDS:
        if not isinstance(payload[field], list):
            raise VisionAnalysisError(f"VL поле {field} должно быть массивом.")
    if not isinstance(payload["series_title_ru"], str) or not isinstance(
        payload["summary_ru"], str
    ):
        raise VisionAnalysisError("VL title/summary должны быть строками.")
    if isinstance(payload["people_count"], bool) or not isinstance(
        payload["people_count"], int
    ):
        raise VisionAnalysisError("VL people_count должен быть целым числом.")
    if isinstance(payload["confidence"], bool) or not isinstance(payload["confidence"], int):
        raise VisionAnalysisError("VL confidence должен быть целым числом.")


def _validate_structured_shape(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    structured = payload.get("structured")
    if not isinstance(structured, dict):
        raise VisionAnalysisError("VL structured profile должен быть объектом.")
    missing = [field for field in _STRUCTURED_FIELDS if field not in structured]
    if missing:
        raise VisionAnalysisError(
            "VL structured profile не содержит обязательные поля: " + ", ".join(missing)
        )
    for field in ("subjects", "visible_text", "uncertainties", "generation_risks"):
        if not isinstance(structured[field], list):
            raise VisionAnalysisError(f"VL structured.{field} должен быть массивом.")
    for field in (
        "composition",
        "pose",
        "camera",
        "body_visibility",
        "covering_method",
        "environment",
        "lighting",
    ):
        if not isinstance(structured[field], dict):
            raise VisionAnalysisError(f"VL structured.{field} должен быть объектом.")
    return structured


def _bounded_strings(value: object, *, limit: int) -> list[str]:
    values = value if isinstance(value, list) else []
    result: list[str] = []
    for item in values:
        text = " ".join(str(item or "").split()).strip()[:300]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _bounded_list_of_objects(value: object, *, limit: int) -> list[dict[str, object]]:
    values = value if isinstance(value, list) else []
    return [_bounded_object(item) for item in values[:limit] if isinstance(item, dict)]


def _bounded_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, object] = {}
    for key, item in list(value.items())[:40]:
        normalized_key = " ".join(str(key or "").split()).strip()[:80]
        if not normalized_key:
            continue
        if isinstance(item, list):
            result[normalized_key] = _bounded_strings(item, limit=20)
        elif isinstance(item, dict):
            result[normalized_key] = {
                " ".join(str(child_key or "").split()).strip()[:80]:
                " ".join(str(child_value or "").split()).strip()[:300]
                for child_key, child_value in list(item.items())[:20]
                if str(child_key or "").strip()
            }
        elif isinstance(item, (bool, int, float)) or item is None:
            result[normalized_key] = item
        else:
            result[normalized_key] = " ".join(str(item).split()).strip()[:300]
    return result


__all__ = (
    "PROFILE_SCHEMA_VERSION",
    "SENSITIVE_PROFILE_SCHEMA",
    "STANDARD_PROFILE_SCHEMA",
    "normalize_routed_profile",
    "prompt_for_mode",
    "schema_for_mode",
)
