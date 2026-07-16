from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from PIL import Image, ImageOps, UnidentifiedImageError

from velvet_bot.database import Database

logger = logging.getLogger(__name__)

_ANALYSIS_VERSION = 1
_MAX_IMAGE_SIDE = 1280
_LIST_FIELDS = (
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
_FIELD_WEIGHTS = {
    "series_keywords": 25,
    "themes": 20,
    "settings": 15,
    "genres": 10,
    "eras": 10,
    "environment": 8,
    "objects": 5,
    "wardrobe": 3,
    "composition": 2,
    "lighting": 1,
    "palette": 1,
}
_ANCHOR_FIELDS = ("series_keywords", "themes", "settings", "genres", "eras")
_GENERIC_TERMS = {
    "art",
    "artwork",
    "character",
    "cinematic",
    "digital art",
    "illustration",
    "image",
    "indoor",
    "outdoor",
    "person",
    "photo",
    "photography",
    "portrait",
    "realistic",
    "scene",
    "woman",
    "man",
    "adult",
}
_ALIASES = {
    "wild west": "western",
    "old west": "western",
    "cowboy": "western",
    "cowboys": "western",
    "western genre": "western",
    "western style": "western",
    "sci fi": "science fiction",
    "sci-fi": "science fiction",
    "science-fiction": "science fiction",
    "cyber punk": "cyberpunk",
    "medieval fantasy": "medieval",
    "victorian era": "victorian",
    "19th-century": "19th century",
    "nineteenth century": "19th century",
}
_TERM_RE = re.compile(r"[^\wа-яё -]+", re.IGNORECASE)

_PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
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
        "confidence": {"type": "integer"},
    },
    "required": [
        "series_title_ru",
        "summary_ru",
        *_LIST_FIELDS,
        "people_count",
        "confidence",
    ],
}

_ANALYSIS_PROMPT = """
Проанализируй изображение для группировки художественного архива в тематические
сеты. Игнорируй личность, лицо, имя, пол и уникальную внешность персонажа. Нельзя
угадывать реальных людей или чувствительные характеристики. Нужны только общие
признаки, которые могут повторяться у изображений с совершенно разными
персонажами: тема, жанр, эпоха, локация, окружение, предметы, одежда, действие,
композиция, ракурс, свет, палитра и настроение.

Пример: изображения разных персонажей в ковбойских шляпах, салуне, пустыне или
на ранчо должны иметь общий ключ western и предлагаться как серия «Дикий Запад»,
даже если лица, позы и фон отличаются.

Верни только JSON по предоставленной схеме. series_title_ru и summary_ru пиши
по-русски. Все элементы массивов пиши короткими устойчивыми терминами на
английском в lower case. series_keywords должны содержать 2–8 наиболее важных
понятий серии, без слов portrait, person, man, woman, photo, image и character.
Не описывай откровенные анатомические подробности: для группировки достаточно
нейтральных художественных и композиционных признаков.
""".strip()


class VisionAnalysisError(RuntimeError):
    pass


class VisionProviderUnavailable(VisionAnalysisError):
    pass


@dataclass(frozen=True, slots=True)
class VisionAnalysisTarget:
    media_id: int
    telegram_file_id: str
    preview_file_id: str | None
    mime_type: str | None


@dataclass(frozen=True, slots=True)
class AIProfileSummary:
    pending: int
    processing: int
    ready: int
    errors: int
    skipped: int


@dataclass(frozen=True, slots=True)
class SemanticProfileMatch:
    score: int
    common_terms: tuple[str, ...]
    common_fields: tuple[str, ...]


def _normalize_term(value: Any) -> str:
    text = " ".join(str(value or "").casefold().strip().split())
    text = _TERM_RE.sub(" ", text)
    text = " ".join(text.split()).strip(" -")
    if not text:
        return ""
    text = _ALIASES.get(text, text)
    if text in _GENERIC_TERMS:
        return ""
    return text[:80]


def _normalize_text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def normalize_ai_profile(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VisionAnalysisError("ИИ вернул не объект JSON.")

    profile: dict[str, Any] = {
        "series_title_ru": _normalize_text(payload.get("series_title_ru"), limit=120),
        "summary_ru": _normalize_text(payload.get("summary_ru"), limit=700),
    }
    for field in _LIST_FIELDS:
        raw_values = payload.get(field)
        values = raw_values if isinstance(raw_values, list) else []
        normalized: list[str] = []
        for value in values:
            term = _normalize_term(value)
            if term and term not in normalized:
                normalized.append(term)
            if len(normalized) >= 12:
                break
        profile[field] = normalized

    try:
        people_count = int(payload.get("people_count", 0))
    except (TypeError, ValueError):
        people_count = 0
    try:
        confidence = int(payload.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    profile["people_count"] = max(0, min(people_count, 50))
    profile["confidence"] = max(0, min(confidence, 100))

    if not profile["series_title_ru"]:
        profile["series_title_ru"] = "Тематический сет"
    if not profile["summary_ru"]:
        profile["summary_ru"] = "Смысловой профиль изображения."
    if not any(profile[field] for field in _ANCHOR_FIELDS):
        raise VisionAnalysisError("ИИ не вернул значимых признаков темы или окружения.")
    return profile


def profile_to_semantic_text(profile: dict[str, Any]) -> str:
    parts = [profile.get("series_title_ru", ""), profile.get("summary_ru", "")]
    for field in _LIST_FIELDS:
        values = profile.get(field)
        if isinstance(values, list) and values:
            parts.append(f"{field}: {', '.join(str(value) for value in values)}")
    return "\n".join(part for part in parts if part).strip()[:6000]


def _profile_terms(profile: dict[str, Any] | None, field: str) -> set[str]:
    if not isinstance(profile, dict):
        return set()
    values = profile.get(field)
    if not isinstance(values, list):
        return set()
    return {term for value in values if (term := _normalize_term(value))}


def compare_semantic_profiles(
    first: dict[str, Any] | None,
    second: dict[str, Any] | None,
) -> SemanticProfileMatch:
    if not isinstance(first, dict) or not isinstance(second, dict):
        return SemanticProfileMatch(score=0, common_terms=(), common_fields=())

    score = 0.0
    common_terms: set[str] = set()
    common_fields: list[str] = []
    anchor_found = False
    for field, weight in _FIELD_WEIGHTS.items():
        first_terms = _profile_terms(first, field)
        second_terms = _profile_terms(second, field)
        if not first_terms or not second_terms:
            continue
        shared = first_terms & second_terms
        if not shared:
            continue
        coefficient = len(shared) / min(len(first_terms), len(second_terms))
        score += weight * coefficient
        common_terms.update(shared)
        common_fields.append(field)
        if field in _ANCHOR_FIELDS:
            anchor_found = True

    first_title = _normalize_term(first.get("series_title_ru"))
    second_title = _normalize_term(second.get("series_title_ru"))
    if first_title and first_title == second_title:
        score += 8
        common_terms.add(first_title)
        common_fields.append("series_title")
        anchor_found = True

    if not anchor_found:
        score = min(score, 35)

    first_confidence = max(0, min(int(first.get("confidence", 0) or 0), 100))
    second_confidence = max(0, min(int(second.get("confidence", 0) or 0), 100))
    confidence_factor = max(0.65, min(first_confidence, second_confidence) / 100)
    final_score = max(0, min(100, round(score * confidence_factor)))
    return SemanticProfileMatch(
        score=final_score,
        common_terms=tuple(sorted(common_terms)),
        common_fields=tuple(dict.fromkeys(common_fields)),
    )


def build_semantic_set_title(profiles: list[dict[str, Any]]) -> str:
    titles = [
        _normalize_text(profile.get("series_title_ru"), limit=120)
        for profile in profiles
        if isinstance(profile, dict)
    ]
    titles = [title for title in titles if title and title != "Тематический сет"]
    if titles:
        title, count = Counter(titles).most_common(1)[0]
        if count >= 2 or len(profiles) == 2:
            return title[:160]

    shared: set[str] | None = None
    for profile in profiles:
        terms = set()
        for field in ("series_keywords", "themes", "genres", "settings", "eras"):
            terms.update(_profile_terms(profile, field))
        shared = terms if shared is None else shared & terms
    if shared:
        return " · ".join(sorted(shared)[:3]).title()[:160]
    return "Тематический сет"


def build_semantic_reason(profiles: list[dict[str, Any]]) -> str:
    common: set[str] | None = None
    for profile in profiles:
        terms = set()
        for field in _ANCHOR_FIELDS:
            terms.update(_profile_terms(profile, field))
        common = terms if common is None else common & terms
    labels = sorted(common or ())[:8]
    if labels:
        return "ИИ нашёл общий смысл независимо от персонажей: " + ", ".join(labels) + "."
    return "ИИ нашёл совпадение темы, окружения и художественного контекста."


def _extract_json_object(value: str) -> dict[str, Any]:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise VisionAnalysisError("ИИ не вернул JSON.")
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as error:
            raise VisionAnalysisError("Ответ ИИ содержит повреждённый JSON.") from error
    if not isinstance(payload, dict):
        raise VisionAnalysisError("ИИ вернул JSON неподходящего типа.")
    return payload


def _prepare_image(source: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(source)) as opened:
            transposed = ImageOps.exif_transpose(opened)
            transposed.load()
            image = transposed.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise VisionAnalysisError("Файл не удалось прочитать как изображение.") from error

    try:
        image.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=86, optimize=True)
        return output.getvalue()
    finally:
        image.close()


class VisionClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: int,
    ) -> None:
        cleaned_provider = provider.strip().casefold()
        if cleaned_provider not in {"ollama", "openai_compatible"}:
            raise ValueError("AI_VISION_PROVIDER должен быть ollama или openai_compatible.")
        self.provider = cleaned_provider
        self.base_url = base_url.strip().rstrip("/")
        self.model = model.strip()
        self.api_key = api_key.strip() if api_key else None
        self.timeout_seconds = max(10, min(int(timeout_seconds), 600))
        if not self.base_url:
            raise ValueError("AI_VISION_BASE_URL не может быть пустым.")
        if not self.model:
            raise ValueError("AI_VISION_MODEL не может быть пустым.")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _read_json(request: urllib.request.Request, *, timeout: int) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise VisionProviderUnavailable(str(error)) from error
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise VisionAnalysisError("Сервис ИИ вернул некорректный HTTP-ответ.") from error
        if not isinstance(payload, dict):
            raise VisionAnalysisError("Сервис ИИ вернул неожиданный формат ответа.")
        return payload

    async def health(self) -> bool:
        if self.provider == "ollama":
            url = f"{self.base_url}/api/tags"
        else:
            root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
            url = f"{root}/v1/models"
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            await asyncio.to_thread(self._read_json, request, timeout=min(10, self.timeout_seconds))
        except VisionAnalysisError:
            return False
        return True

    async def analyze(self, source: bytes) -> dict[str, Any]:
        prepared = await asyncio.to_thread(_prepare_image, source)
        image_base64 = base64.b64encode(prepared).decode("ascii")
        if self.provider == "ollama":
            url = f"{self.base_url}/api/chat"
            body = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": _ANALYSIS_PROMPT,
                        "images": [image_base64],
                    }
                ],
                "format": _PROFILE_SCHEMA,
                "stream": False,
                "think": False,
                "options": {"temperature": 0},
            }
        else:
            root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
            url = f"{root}/v1/chat/completions"
            body = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _ANALYSIS_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                },
                            },
                        ],
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": 1200,
            }

        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        payload = await asyncio.to_thread(
            self._read_json,
            request,
            timeout=self.timeout_seconds,
        )
        if self.provider == "ollama":
            content = ((payload.get("message") or {}).get("content") or "")
        else:
            choices = payload.get("choices") or []
            content = (
                ((choices[0] or {}).get("message") or {}).get("content")
                if choices
                else ""
            )
        return normalize_ai_profile(_extract_json_object(str(content or "")))


class MediaAIRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def claim_targets(
        self,
        *,
        provider: str,
        model: str,
        max_attempts: int,
        limit: int = 1,
    ) -> tuple[VisionAnalysisTarget, ...]:
        safe_limit = max(1, min(int(limit), 4))
        safe_attempts = max(1, min(int(max_attempts), 10))
        async with self._database._require_pool().acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO media_ai_profiles (media_id, status)
                    SELECT mf.id, 'pending'
                    FROM media_files AS mf
                    WHERE mf.media_type = 'photo'
                       OR (mf.media_type = 'document'
                           AND COALESCE(mf.mime_type, '') LIKE 'image/%')
                    ON CONFLICT (media_id) DO NOTHING
                    """
                )
                await connection.execute(
                    """
                    UPDATE media_ai_profiles
                    SET status = 'pending', updated_at = NOW()
                    WHERE status = 'processing'
                      AND updated_at < NOW() - INTERVAL '30 minutes'
                    """
                )
                rows = await connection.fetch(
                    """
                    SELECT p.media_id, mf.telegram_file_id, mf.preview_file_id,
                           mf.mime_type
                    FROM media_ai_profiles AS p
                    JOIN media_files AS mf ON mf.id = p.media_id
                    WHERE (
                            p.status = 'pending'
                            OR (p.status = 'error' AND p.attempt_count < $1::SMALLINT)
                          )
                      AND mf.media_set_id IS NULL
                    ORDER BY p.updated_at, p.media_id
                    FOR UPDATE OF p SKIP LOCKED
                    LIMIT $2::INTEGER
                    """,
                    safe_attempts,
                    safe_limit,
                )
                if rows:
                    await connection.execute(
                        """
                        UPDATE media_ai_profiles
                        SET status = 'processing', provider = $2::VARCHAR,
                            model = $3::VARCHAR, analysis_version = $4::SMALLINT,
                            attempt_count = attempt_count + 1,
                            error_message = NULL, updated_at = NOW()
                        WHERE media_id = ANY($1::BIGINT[])
                        """,
                        [int(row["media_id"]) for row in rows],
                        provider,
                        model[:160],
                        _ANALYSIS_VERSION,
                    )
        return tuple(
            VisionAnalysisTarget(
                media_id=int(row["media_id"]),
                telegram_file_id=str(row["telegram_file_id"]),
                preview_file_id=(
                    str(row["preview_file_id"])
                    if row["preview_file_id"] is not None
                    else None
                ),
                mime_type=row["mime_type"],
            )
            for row in rows
        )

    async def mark_ready(self, media_id: int, profile: dict[str, Any]) -> None:
        async with self._database._require_pool().acquire() as connection:
            await connection.execute(
                """
                UPDATE media_ai_profiles
                SET status = 'ready', analysis = $2::JSONB,
                    semantic_text = $3::TEXT, error_message = NULL,
                    analyzed_at = NOW(), updated_at = NOW()
                WHERE media_id = $1::BIGINT
                """,
                int(media_id),
                json.dumps(profile, ensure_ascii=False),
                profile_to_semantic_text(profile),
            )

    async def mark_error(
        self,
        media_id: int,
        error: BaseException,
        *,
        max_attempts: int,
        permanent: bool = False,
    ) -> None:
        async with self._database._require_pool().acquire() as connection:
            await connection.execute(
                """
                UPDATE media_ai_profiles
                SET status = CASE
                        WHEN $3::BOOLEAN OR attempt_count >= $4::SMALLINT
                            THEN 'skipped'
                        ELSE 'error'
                    END,
                    error_message = $2::TEXT,
                    updated_at = NOW()
                WHERE media_id = $1::BIGINT
                """,
                int(media_id),
                str(error)[:2000],
                bool(permanent),
                max(1, min(int(max_attempts), 10)),
            )

    async def summary(self) -> AIProfileSummary:
        async with self._database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'processing') AS processing,
                    COUNT(*) FILTER (WHERE status = 'ready') AS ready,
                    COUNT(*) FILTER (WHERE status = 'error') AS errors,
                    COUNT(*) FILTER (WHERE status = 'skipped') AS skipped
                FROM media_ai_profiles
                """
            )
        return AIProfileSummary(
            pending=int(row["pending"] or 0),
            processing=int(row["processing"] or 0),
            ready=int(row["ready"] or 0),
            errors=int(row["errors"] or 0),
            skipped=int(row["skipped"] or 0),
        )


class MediaAIVisionService:
    def __init__(
        self,
        *,
        bot: Bot,
        repository: MediaAIRepository,
        client: VisionClient,
        max_attempts: int = 3,
    ) -> None:
        self._bot = bot
        self._repository = repository
        self._client = client
        self._max_attempts = max(1, min(int(max_attempts), 10))
        self._last_health_check = 0.0
        self._healthy = False
        self._last_warning = 0.0

    async def _provider_available(self) -> bool:
        now = time.monotonic()
        if now - self._last_health_check < 30:
            return self._healthy
        self._last_health_check = now
        self._healthy = await self._client.health()
        if not self._healthy and now - self._last_warning >= 300:
            self._last_warning = now
            logger.warning(
                "AI vision service is unavailable provider=%s base_url=%s model=%s. "
                "The bot continues without semantic analysis.",
                self._client.provider,
                self._client.base_url,
                self._client.model,
            )
        return self._healthy

    async def _download_target(self, target: VisionAnalysisTarget) -> bytes:
        errors: list[BaseException] = []
        file_ids = [target.telegram_file_id]
        if target.preview_file_id and target.preview_file_id not in file_ids:
            file_ids.append(target.preview_file_id)
        for file_id in file_ids:
            try:
                destination = io.BytesIO()
                await self._bot.download(file_id, destination=destination, seek=True)
                value = destination.getvalue()
                if value:
                    return value
            except (TelegramBadRequest, TelegramAPIError) as error:
                errors.append(error)
        if errors:
            raise VisionAnalysisError(str(errors[-1]))
        raise VisionAnalysisError("Telegram вернул пустое изображение.")

    async def process_once(self) -> int:
        if not await self._provider_available():
            return 0
        targets = await self._repository.claim_targets(
            provider=self._client.provider,
            model=self._client.model,
            max_attempts=self._max_attempts,
            limit=1,
        )
        processed = 0
        for target in targets:
            try:
                source = await self._download_target(target)
                profile = await self._client.analyze(source)
                await self._repository.mark_ready(target.media_id, profile)
                processed += 1
                logger.info(
                    "AI semantic profile ready media_id=%s title=%s",
                    target.media_id,
                    profile.get("series_title_ru"),
                )
            except asyncio.CancelledError:
                raise
            except VisionProviderUnavailable as error:
                self._healthy = False
                await self._repository.mark_error(
                    target.media_id,
                    error,
                    max_attempts=self._max_attempts,
                )
                break
            except Exception as error:
                logger.warning(
                    "AI semantic analysis failed media_id=%s: %s",
                    target.media_id,
                    error,
                )
                permanent = isinstance(error, VisionAnalysisError) and (
                    "прочитать как изображение" in str(error)
                    or "file is too big" in str(error).casefold()
                )
                await self._repository.mark_error(
                    target.media_id,
                    error,
                    max_attempts=self._max_attempts,
                    permanent=permanent,
                )
        return processed


__all__ = (
    "AIProfileSummary",
    "MediaAIRepository",
    "MediaAIVisionService",
    "SemanticProfileMatch",
    "VisionAnalysisError",
    "VisionClient",
    "build_semantic_reason",
    "build_semantic_set_title",
    "compare_semantic_profiles",
    "normalize_ai_profile",
    "profile_to_semantic_text",
)
