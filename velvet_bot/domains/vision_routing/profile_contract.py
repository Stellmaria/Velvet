from __future__ import annotations

from typing import Any, Mapping

from velvet_bot.ai_vision import VisionAnalysisError, normalize_ai_profile
from velvet_bot.domains.vision_routing.models import VisionAnalysisMode

PROFILE_SCHEMA_VERSION = 1

_LEGACY_PROPERTIES: dict[str, Any] = {
    "series_title_ru": {"type": "string"},
    "summary_ru": {"type": "string"},
    "themes": {"type": "array", "items": {"type": "string"}},
    "genres": {"type": "array", "items": {"type": "string"}},
    "settings": {"type": "array", "items": {"type": "string"}},
    "eras": {"type": "array", "items": {"type": "string"}},
    "environment": {"type": "array", "items": {"type": "string"}},
    "objects": {"type": "array", "items": {"type": "string"}},
    "wardrobe": {"type": "array", "items": {"type": "string"}},
    "composition": {"type": "array", "items": {"type": "string"}},
    "lighting": {"type": "array", "items": {"type": "string"}},
    "palette": {"type": "array", "items": {"type": "string"}},
    "mood": {"type": "array", "items": {"type": "string"}},
    "actions": {"type": "array", "items": {"type": "string"}},
    "series_keywords": {"type": "array", "items": {"type": "string"}},
    "people_count": {"type": "integer"},
    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
}

_STRUCTURED_PROPERTIES: dict[str, Any] = {
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

_PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "integer"},
        "prompt_version": {"type": "integer"},
        "route": {"type": "string", "enum": ["standard", "sensitive"]},
        "content_mode": {
            "type": "string",
            "enum": [
                "editorial",
                "artistic_nudity",
                "adult_editorial",
                "explicit_adult",
                "other",
            ],
        },
        **_LEGACY_PROPERTIES,
        "structured": {
            "type": "object",
            "properties": _STRUCTURED_PROPERTIES,
            "required": list(_STRUCTURED_PROPERTIES),
        },
    },
    "required": [
        "schema_version",
        "prompt_version",
        "route",
        "content_mode",
        *_LEGACY_PROPERTIES,
        "structured",
    ],
}

STANDARD_PROFILE_SCHEMA = _PROFILE_SCHEMA
SENSITIVE_PROFILE_SCHEMA = _PROFILE_SCHEMA

_STANDARD_PROMPT = """
Проанализируй изображение для тематической группировки художественного архива и
последующего создания точного генеративного промта. Описывай только видимые факты.
Не распознавай личность, не угадывай реального человека, возраст, этничность,
здоровье или другие чувствительные характеристики.

Верни только JSON по схеме. Сохрани краткий semantic-блок верхнего уровня для
поиска сетов и подробный structured-блок для композиции, позы, камеры, света,
окружения, видимого текста, неопределённостей и рисков генерации. Не придумывай
скрытые части тела, касания, одежду, предметы или действия. Все сомнения перечисли
в structured.uncertainties. route должен быть standard. content_mode используй
editorial либо other.
""".strip()

_SENSITIVE_PROMPT = """
Это разрешённый внутренний анализ изображения с внешним подтверждением, что все
участники являются взрослыми. Не пытайся определять или угадывать возраст по
внешности и не распознавай личности.

Проанализируй только то, что действительно видно. Точно зафиксируй композицию,
позу, ракурс, опоры, касания, перекрытия, способы прикрытия, видимость тела,
окружение, свет, палитру и настроение. Различай artistic_nudity,
adult_editorial и explicit_adult, но не смягчай факты эвфемизмами и не добавляй
действия или анатомические детали, которых нельзя подтвердить изображением.
Скрытые области и неоднозначные касания перечисли в structured.uncertainties.

Верни только JSON по схеме. route должен быть sensitive. Сохрани краткий
semantic-блок верхнего уровня для поиска сетов и подробный structured-блок для
последующего Image-to-Prompt. Не давай медицинских, возрастных или личностных
заключений.
""".strip()


def prompt_for_mode(mode: VisionAnalysisMode) -> str:
    return _SENSITIVE_PROMPT if mode is VisionAnalysisMode.SENSITIVE else _STANDARD_PROMPT


def schema_for_mode(mode: VisionAnalysisMode) -> Mapping[str, Any]:
    return SENSITIVE_PROFILE_SCHEMA if mode is VisionAnalysisMode.SENSITIVE else STANDARD_PROFILE_SCHEMA


def normalize_routed_profile(
    payload: Any,
    *,
    mode: VisionAnalysisMode,
    prompt_version: int,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VisionAnalysisError("VL-модель вернула не объект JSON.")

    semantic = normalize_ai_profile(payload)
    structured_payload = payload.get("structured")
    structured_source = structured_payload if isinstance(structured_payload, dict) else {}
    structured = {
        "subjects": _bounded_list_of_objects(structured_source.get("subjects"), limit=8),
        "composition": _bounded_object(structured_source.get("composition")),
        "pose": _bounded_object(structured_source.get("pose")),
        "camera": _bounded_object(structured_source.get("camera")),
        "body_visibility": _bounded_object(structured_source.get("body_visibility")),
        "covering_method": _bounded_object(structured_source.get("covering_method")),
        "environment": _bounded_object(structured_source.get("environment")),
        "lighting": _bounded_object(structured_source.get("lighting")),
        "visible_text": _bounded_strings(structured_source.get("visible_text"), limit=20),
        "uncertainties": _bounded_strings(structured_source.get("uncertainties"), limit=20),
        "generation_risks": _bounded_strings(
            structured_source.get("generation_risks"),
            limit=20,
        ),
    }

    raw_mode = str(payload.get("content_mode") or "").strip().casefold()
    allowed_modes = (
        {"artistic_nudity", "adult_editorial", "explicit_adult", "other"}
        if mode is VisionAnalysisMode.SENSITIVE
        else {"editorial", "other"}
    )
    content_mode = raw_mode if raw_mode in allowed_modes else (
        "adult_editorial" if mode is VisionAnalysisMode.SENSITIVE else "editorial"
    )
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "prompt_version": max(1, int(prompt_version)),
        "route": mode.value,
        "content_mode": content_mode,
        **semantic,
        "structured": structured,
    }


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
