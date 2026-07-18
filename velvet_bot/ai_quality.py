from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

from aiogram import Bot

from velvet_bot.ai_vision import (
    VisionAnalysisError,
    VisionAnalysisTarget,
    VisionClient,
    VisionProviderUnavailable,
    _extract_json_object,
    _prepare_image,
)
from velvet_bot.database import Database
from velvet_bot.resilient_ai_vision import ResilientMediaAIVisionService

logger = logging.getLogger(__name__)

_ANALYSIS_VERSION = 1
_CHECK_KEYS = (
    "anatomy",
    "hands",
    "face",
    "hair",
    "skin_texture",
    "lighting",
    "exposure",
    "sharpness",
    "background",
    "reflections",
    "composition",
    "compression",
    "text_watermarks",
    "ui_artifacts",
)

_QUALITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "quality_score": {"type": "integer"},
        "confidence": {"type": "integer"},
        "verdict": {"type": "string", "enum": ["ready", "review", "critical"]},
        "summary_ru": {"type": "string"},
        "critical_issues": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "uncertain_areas": {"type": "array", "items": {"type": "string"}},
        "checks": {
            "type": "object",
            "properties": {key: {"type": "integer"} for key in _CHECK_KEYS},
            "required": list(_CHECK_KEYS),
            "additionalProperties": False,
        },
    },
    "required": [
        "quality_score",
        "confidence",
        "verdict",
        "summary_ru",
        "critical_issues",
        "warnings",
        "strengths",
        "uncertain_areas",
        "checks",
    ],
    "additionalProperties": False,
}

_QUALITY_PROMPT = """
Ты выполняешь профессиональную техническую проверку качества художественного
изображения перед публикацией в канале Velvet Anatomy.

На изображении могут быть взрослые персонажи и художественная обнажённость. Не
отказывайся от анализа, не морализируй и не оценивай допустимость сюжета. Описывай
только нейтральные визуальные, технические и композиционные признаки. Не пытайся
установить личность человека, имя, возраст, происхождение или чувствительные
характеристики.

Проверь только то, что действительно видно:
- генеративные дефекты анатомии, рук, пальцев, лица, глаз, зубов и волос;
- неестественное слияние тела, волос, предметов и фона;
- повреждённые отражения, повторяющиеся или плавающие объекты;
- пластиковую кожу, чрезмерное сглаживание и странную текстуру;
- резкость, смаз, шум, JPEG-артефакты и низкое разрешение;
- пересвет, проваленные тени и несогласованный свет;
- неудачные обрезания, нарушенный баланс и композиционные ошибки;
- водяные знаки, посторонний текст, интерфейс, рамки и служебные элементы.

critical_issues используй только для явных дефектов, из-за которых работу разумно
вернуть на исправление. warnings используй для заметных, но не фатальных проблем.
Не придумывай скрытые дефекты и не выдавай неуверенное предположение за факт.
uncertain_areas заполняй, когда качество или ракурс не позволяют сделать вывод.
Все тексты пиши по-русски, кратко и предметно.
""".strip()


def _clamp_score(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, min(number, 100))


def _normalize_strings(value: Any, *, limit: int = 8, length: int = 260) -> list[str]:
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


def normalize_quality_report(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VisionAnalysisError("Qwen вернул отчёт качества не в виде JSON-объекта.")

    critical = _normalize_strings(payload.get("critical_issues"))
    warnings = _normalize_strings(payload.get("warnings"))
    strengths = _normalize_strings(payload.get("strengths"), limit=6)
    uncertain = _normalize_strings(payload.get("uncertain_areas"), limit=6)

    if critical:
        verdict = "critical"
    elif warnings:
        verdict = "review"
    else:
        verdict = "ready"

    checks_raw = payload.get("checks")
    checks_raw = checks_raw if isinstance(checks_raw, dict) else {}
    checks = {key: _clamp_score(checks_raw.get(key, 0)) for key in _CHECK_KEYS}

    summary = " ".join(str(payload.get("summary_ru") or "").split()).strip()[:700]
    if not summary:
        summary = {
            "critical": "Обнаружены заметные дефекты, требующие проверки владельцем.",
            "review": "Работа требует ручной проверки перед публикацией.",
            "ready": "Явных технических дефектов не обнаружено.",
        }[verdict]

    quality_score = _clamp_score(payload.get("quality_score"))
    confidence = _clamp_score(payload.get("confidence"))
    if confidence <= 0:
        confidence = 50

    return {
        "quality_score": quality_score,
        "confidence": confidence,
        "verdict": verdict,
        "summary_ru": summary,
        "critical_issues": critical,
        "warnings": warnings,
        "strengths": strengths,
        "uncertain_areas": uncertain,
        "checks": checks,
    }


@dataclass(frozen=True, slots=True)
class AIQualitySummary:
    pending: int
    processing: int
    ready: int
    errors: int
    skipped: int
    unreviewed: int
    accepted: int
    fix_required: int
    clean: int
    warnings: int
    critical: int


@dataclass(frozen=True, slots=True)
class AIQualityItem:
    media_id: int
    file_name: str
    media_type: str
    telegram_file_id: str
    preview_file_id: str | None
    status: str
    verdict: str | None
    quality_score: int | None
    confidence: int | None
    report: dict[str, Any] | None
    decision: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class AIQualityPage:
    items: tuple[AIQualityItem, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


def _decode_report(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


class AIQualityRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _item_from_row(row: Any) -> AIQualityItem:
        return AIQualityItem(
            media_id=int(row["media_id"]),
            file_name=str(row["file_name"] or f"media-{row['media_id']}"),
            media_type=str(row["media_type"]),
            telegram_file_id=str(row["telegram_file_id"]),
            preview_file_id=(
                str(row["preview_file_id"])
                if row["preview_file_id"] is not None
                else None
            ),
            status=str(row["status"]),
            verdict=str(row["verdict"]) if row["verdict"] is not None else None,
            quality_score=(
                int(row["quality_score"])
                if row["quality_score"] is not None
                else None
            ),
            confidence=int(row["confidence"]) if row["confidence"] is not None else None,
            report=_decode_report(row["report"]),
            decision=str(row["decision"]) if row["decision"] is not None else None,
            error_message=(
                str(row["error_message"])
                if row["error_message"] is not None
                else None
            ),
        )

    async def claim_targets(
        self,
        *,
        provider: str,
        model: str,
        max_attempts: int,
        limit: int = 1,
    ) -> tuple[VisionAnalysisTarget, ...]:
        safe_limit = max(1, min(int(limit), 2))
        safe_attempts = max(1, min(int(max_attempts), 10))
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO media_ai_quality_checks (media_id, status)
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
                    UPDATE media_ai_quality_checks
                    SET status = 'pending', updated_at = NOW()
                    WHERE status = 'processing'
                      AND updated_at < NOW() - INTERVAL '30 minutes'
                    """
                )
                rows = await connection.fetch(
                    """
                    SELECT q.media_id, mf.telegram_file_id, mf.preview_file_id,
                           mf.mime_type
                    FROM media_ai_quality_checks AS q
                    JOIN media_files AS mf ON mf.id = q.media_id
                    WHERE q.decision IS NULL
                      AND (
                            q.status = 'pending'
                            OR (q.status = 'error' AND q.attempt_count < $1::SMALLINT)
                          )
                    ORDER BY q.media_id DESC
                    FOR UPDATE OF q SKIP LOCKED
                    LIMIT $2::INTEGER
                    """,
                    safe_attempts,
                    safe_limit,
                )
                if rows:
                    await connection.execute(
                        """
                        UPDATE media_ai_quality_checks
                        SET status = 'processing', provider = $2::VARCHAR,
                            model = $3::VARCHAR, analysis_version = $4::SMALLINT,
                            attempt_count = attempt_count + 1,
                            error_message = NULL, updated_at = NOW()
                        WHERE media_id = ANY($1::BIGINT[])
                        """,
                        [int(row["media_id"]) for row in rows],
                        provider[:64],
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

    async def mark_ready(self, media_id: int, report: dict[str, Any]) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_ai_quality_checks
                SET status = 'ready', verdict = $2::VARCHAR,
                    quality_score = $3::SMALLINT, confidence = $4::SMALLINT,
                    report = $5::JSONB, error_message = NULL,
                    analyzed_at = NOW(), updated_at = NOW()
                WHERE media_id = $1::BIGINT
                """,
                int(media_id),
                str(report["verdict"]),
                int(report["quality_score"]),
                int(report["confidence"]),
                json.dumps(report, ensure_ascii=False),
            )

    async def mark_error(
        self,
        media_id: int,
        error: BaseException,
        *,
        max_attempts: int,
        permanent: bool = False,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_ai_quality_checks
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

    async def summary(self) -> AIQualitySummary:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'processing') AS processing,
                    COUNT(*) FILTER (WHERE status = 'ready') AS ready,
                    COUNT(*) FILTER (WHERE status = 'error') AS errors,
                    COUNT(*) FILTER (WHERE status = 'skipped') AS skipped,
                    COUNT(*) FILTER (
                        WHERE status = 'ready' AND decision IS NULL
                    ) AS unreviewed,
                    COUNT(*) FILTER (WHERE decision = 'accepted') AS accepted,
                    COUNT(*) FILTER (WHERE decision = 'fix_required') AS fix_required,
                    COUNT(*) FILTER (WHERE status = 'ready' AND verdict = 'ready') AS clean,
                    COUNT(*) FILTER (WHERE status = 'ready' AND verdict = 'review') AS warnings,
                    COUNT(*) FILTER (WHERE status = 'ready' AND verdict = 'critical') AS critical
                FROM media_ai_quality_checks
                """
            )
        return AIQualitySummary(
            **{key: int(row[key] or 0) for key in row.keys()}
        )

    @staticmethod
    def _section_condition(section: str) -> str:
        conditions = {
            "review": "q.status = 'ready' AND q.decision IS NULL",
            "accepted": "q.decision = 'accepted'",
            "fix": "q.decision = 'fix_required'",
            "errors": "q.status IN ('error', 'skipped')",
        }
        if section not in conditions:
            raise ValueError("Неизвестный раздел проверки качества.")
        return conditions[section]

    async def list_items(
        self,
        section: str,
        *,
        page: int = 0,
        page_size: int = 6,
    ) -> AIQualityPage:
        condition = self._section_condition(section)
        safe_size = max(1, min(int(page_size), 10))
        async with self._database.acquire() as connection:
            total = int(
                await connection.fetchval(
                    f"SELECT COUNT(*) FROM media_ai_quality_checks q WHERE {condition}"
                )
                or 0
            )
            total_pages = max(1, (total + safe_size - 1) // safe_size)
            safe_page = min(max(0, int(page)), total_pages - 1)
            offset = safe_page * safe_size
            rows = await connection.fetch(
                f"""
                SELECT q.*, mf.file_name, mf.media_type, mf.telegram_file_id,
                       mf.preview_file_id
                FROM media_ai_quality_checks q
                JOIN media_files mf ON mf.id = q.media_id
                WHERE {condition}
                ORDER BY CASE q.verdict
                            WHEN 'critical' THEN 3
                            WHEN 'review' THEN 2
                            ELSE 1
                         END DESC,
                         q.updated_at DESC,
                         q.media_id DESC
                OFFSET $1::INTEGER LIMIT $2::INTEGER
                """,
                offset,
                safe_size,
            )
        return AIQualityPage(
            items=tuple(self._item_from_row(row) for row in rows),
            page=safe_page,
            page_size=safe_size,
            total_items=total,
        )

    async def get_item(self, media_id: int) -> AIQualityItem | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT q.*, mf.file_name, mf.media_type, mf.telegram_file_id,
                       mf.preview_file_id
                FROM media_ai_quality_checks q
                JOIN media_files mf ON mf.id = q.media_id
                WHERE q.media_id = $1::BIGINT
                """,
                int(media_id),
            )
        return self._item_from_row(row) if row is not None else None

    async def set_decision(self, media_id: int, decision: str, user_id: int) -> bool:
        if decision not in {"accepted", "fix_required"}:
            raise ValueError("Неизвестное решение проверки качества.")
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_ai_quality_checks
                SET decision = $2::VARCHAR, decided_by = $3::BIGINT,
                    decided_at = NOW(), updated_at = NOW()
                WHERE media_id = $1::BIGINT AND status = 'ready'
                """,
                int(media_id),
                decision,
                int(user_id),
            )
        return result.endswith("1")

    async def retry(self, media_id: int) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_ai_quality_checks
                SET status = 'pending', attempt_count = 0,
                    verdict = NULL, quality_score = NULL, confidence = NULL,
                    report = NULL, decision = NULL, decided_by = NULL,
                    decided_at = NULL, error_message = NULL, analyzed_at = NULL,
                    updated_at = NOW()
                WHERE media_id = $1::BIGINT
                """,
                int(media_id),
            )
        return result.endswith("1")


class QualityVisionClient(VisionClient):
    def _schema_prompt(self) -> str:
        return (
            _QUALITY_PROMPT
            + "\n\nВерни только один JSON-объект по этой JSON Schema без markdown "
            + "и пояснений вне JSON:\n"
            + json.dumps(_QUALITY_SCHEMA, ensure_ascii=False, separators=(",", ":"))
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
                return normalize_quality_report(_extract_json_object(text))
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
        raise VisionAnalysisError(f"Qwen не вернул отчёт качества ({diagnostic}).")

    async def analyze(self, source: bytes) -> dict[str, Any]:
        prepared = await asyncio.to_thread(_prepare_image, source)
        image_base64 = base64.b64encode(prepared).decode("ascii")
        prompt = self._schema_prompt()

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
                    "format": _QUALITY_SCHEMA if use_schema else "json",
                    "stream": False,
                    "think": False,
                    "keep_alive": "15m",
                    "options": {"temperature": 0, "num_predict": 1700},
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
                "Qwen не вернул отчёт качества после двух режимов. "
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
            "max_tokens": 1700,
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
        content = (
            ((choices[0] or {}).get("message") or {}).get("content")
            if choices
            else ""
        )
        return normalize_quality_report(_extract_json_object(str(content or "")))


class AIQualityService(ResilientMediaAIVisionService):
    def __init__(
        self,
        *,
        bot: Bot,
        repository: AIQualityRepository,
        client: QualityVisionClient,
        max_attempts: int = 3,
    ) -> None:
        super().__init__(
            bot=bot,
            repository=repository,  # type: ignore[arg-type]
            client=client,
            max_attempts=max_attempts,
        )
        self._repository = repository
        self._client = client
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
                "Qwen quality service is unavailable provider=%s base_url=%s model=%s",
                self._client.provider,
                self._client.base_url,
                self._client.model,
            )
        return self._healthy

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
                report = await self._client.analyze(source)
                await self._repository.mark_ready(target.media_id, report)
                processed += 1
                logger.info(
                    "AI quality report ready media_id=%s verdict=%s score=%s",
                    target.media_id,
                    report.get("verdict"),
                    report.get("quality_score"),
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
            except Exception as error:  # broad-boundary: compensate-claimed-ai-quality
                logger.warning(
                    "AI quality analysis failed media_id=%s: %s",
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
    "AIQualityItem",
    "AIQualityPage",
    "AIQualityRepository",
    "AIQualityService",
    "AIQualitySummary",
    "QualityVisionClient",
    "normalize_quality_report",
)
