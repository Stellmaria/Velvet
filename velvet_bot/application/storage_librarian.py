from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from typing import Protocol, cast

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_content import (
    analysis_prompt,
    chunk_analysis_source,
    extract_storage_text,
    hierarchical_synthesis_source,
    parse_librarian_analysis,
    plan_storage_text_chunks,
    redact_sensitive,
)
from velvet_bot.domains.telegram_storage.librarian_models import (
    HermesRunResult,
    JsonObject,
    JsonValue,
    LibrarianAnalysis,
    LibrarianObject,
    StorageLibrarianError,
    StorageLibrarianSettings,
    TerminalStorageLibrarianError,
    UnsupportedStorageContent,
)
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)

logger = logging.getLogger(__name__)
_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё_-]{3,}")
_ANALYSIS_INSTRUCTIONS = (
    "Ты библиотекарь закрытого Telegram Storage Velvet. Анализируй только "
    "предоставленный текст, не вызывай инструменты и возвращай строгий JSON без "
    "Markdown. Естественный язык ответа — русский; технические идентификаторы не "
    "переводи."
)
_SEARCH_STOPWORDS = frozenset(
    {
        "какие",
        "какой",
        "какая",
        "какое",
        "каких",
        "которые",
        "который",
        "что",
        "чем",
        "где",
        "когда",
        "почему",
        "были",
        "было",
        "есть",
        "это",
        "эти",
        "этот",
        "последних",
        "последние",
        "архиве",
        "материалах",
        "проанализированных",
        "the",
        "what",
        "which",
        "were",
        "was",
        "are",
        "from",
        "with",
        "latest",
    }
)
_RUSSIAN_SUFFIXES = (
    "иями",
    "ями",
    "ами",
    "ение",
    "ения",
    "ений",
    "ениями",
    "остью",
    "ости",
    "овать",
    "ировать",
    "лись",
    "лась",
    "лось",
    "ого",
    "ему",
    "ому",
    "иях",
    "ах",
    "ях",
    "ами",
    "ями",
    "ов",
    "ев",
    "ей",
    "ой",
    "ий",
    "ый",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ам",
    "ям",
    "ом",
    "ем",
    "ия",
    "ья",
    "ы",
    "и",
    "а",
    "я",
    "у",
    "ю",
    "е",
    "о",
)
_ENGLISH_SUFFIXES = ("ingly", "edly", "ing", "ed", "es", "s")


class StorageObjectLoader(Protocol):
    async def download(
        self,
        item: LibrarianObject,
        *,
        max_bytes: int,
    ) -> bytes: ...


class LibrarianRunClient(Protocol):
    async def run(
        self,
        *,
        prompt: str,
        session_id: str,
        instructions: str,
    ) -> HermesRunResult: ...


class LibrarianReportPublisher(Protocol):
    async def publish(
        self,
        item: LibrarianObject,
        analysis: LibrarianAnalysis,
    ) -> None: ...

    async def publish_failure(
        self,
        *,
        object_id: int,
        item: LibrarianObject | None,
        error: BaseException,
    ) -> None: ...


def _json_list(value: object) -> list[JsonValue]:
    if isinstance(value, list):
        return cast(list[JsonValue], value)
    if isinstance(value, str):
        try:
            decoded: object = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return cast(list[JsonValue], decoded)
    return []


def _stem_token(value: str) -> str:
    token = value.casefold().replace("ё", "е").strip("_-")
    if len(token) < 3 or token in _SEARCH_STOPWORDS:
        return ""
    suffixes = _ENGLISH_SUFFIXES if token.isascii() else _RUSSIAN_SUFFIXES
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _search_terms(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for raw in _TOKEN_RE.findall(value):
        token = _stem_token(raw)
        if token and token not in result:
            result.append(token)
    return tuple(result[:16])


def _row_terms(row: dict[str, object]) -> set[str]:
    values = (
        str(row.get("summary") or ""),
        str(row.get("logical_key") or ""),
        str(row.get("original_name") or ""),
        json.dumps(_json_list(row.get("tags")), ensure_ascii=False),
        json.dumps(_json_list(row.get("entities")), ensure_ascii=False),
        json.dumps(_json_list(row.get("action_items")), ensure_ascii=False),
    )
    return {
        token
        for value in values
        for raw in _TOKEN_RE.findall(value)
        if (token := _stem_token(raw))
    }


def _fallback_analysis_rows(
    question: str,
    candidates: list[dict[str, object]],
    *,
    limit: int,
) -> list[dict[str, object]]:
    terms = set(_search_terms(question))
    if not terms:
        return []
    scored: list[tuple[int, dict[str, object]]] = []
    for row in candidates:
        score = len(terms.intersection(_row_terms(row)))
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[: max(1, min(int(limit), 20))]]


def _usage_value(run: HermesRunResult, key: str) -> int:
    value = run.usage.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _aggregate_hierarchical_run(
    runs: tuple[HermesRunResult, ...],
    *,
    chunk_count: int,
) -> HermesRunResult:
    final = runs[-1]
    usage: JsonObject = dict(final.usage)
    usage.update(
        {
            "prompt_tokens": sum(_usage_value(run, "prompt_tokens") for run in runs),
            "completion_tokens": sum(
                _usage_value(run, "completion_tokens") for run in runs
            ),
            "chunk_count": chunk_count,
            "inference_calls": len(runs),
            "hierarchical": True,
        }
    )
    return HermesRunResult(
        run_id=final.run_id,
        output=final.output,
        usage=usage,
        analyzer=final.analyzer,
    )


class StorageLibrarianService:
    def __init__(
        self,
        *,
        database: Database,
        settings: StorageLibrarianSettings,
        object_loader: StorageObjectLoader,
        analysis_client: LibrarianRunClient,
        answer_client: LibrarianRunClient,
        report_publisher: LibrarianReportPublisher | None = None,
    ) -> None:
        self.settings = settings
        self.repository = StorageLibrarianRepository(database)
        self.object_loader = object_loader
        self.analysis_client = analysis_client
        self.answer_client = answer_client
        self.report_publisher = report_publisher
        self.worker_id = f"storage-librarian:{os.getpid()}"

    async def _run_local_analysis(
        self,
        *,
        prompt: str,
        session_id: str,
    ) -> HermesRunResult:
        run = await self.analysis_client.run(
            prompt=prompt,
            session_id=session_id,
            instructions=_ANALYSIS_INSTRUCTIONS,
        )
        if run.analyzer != "ollama":
            raise TerminalStorageLibrarianError(
                "Storage Librarian analysis must use local Ollama only; "
                f"received analyzer={run.analyzer}."
            )
        return run

    async def _analyze_source(
        self,
        item: LibrarianObject,
        source_text: str,
    ) -> HermesRunResult:
        chunks = plan_storage_text_chunks(source_text, settings=self.settings)
        base_session = (
            f"velvet-storage-{item.object_id}-{self.settings.analyzer_version}"
        )
        if len(chunks) == 1:
            return await self._run_local_analysis(
                prompt=analysis_prompt(item, source_text),
                session_id=base_session,
            )

        required_calls = len(chunks) + 1
        if required_calls > self.settings.max_inference_calls:
            raise TerminalStorageLibrarianError(
                "Storage Librarian hierarchical analysis exceeds the bounded inference "
                f"budget: calls={required_calls}, limit={self.settings.max_inference_calls}."
            )

        chunk_runs: list[HermesRunResult] = []
        chunk_analyses: list[LibrarianAnalysis] = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_source = chunk_analysis_source(
                chunk,
                index=index,
                total=len(chunks),
                max_chars=self.settings.max_text_chars,
            )
            run = await self._run_local_analysis(
                prompt=analysis_prompt(item, chunk_source),
                session_id=(
                    f"{base_session}-chunk-{index:03d}-of-{len(chunks):03d}"
                ),
            )
            chunk_runs.append(run)
            chunk_analyses.append(parse_librarian_analysis(run.output))

        synthesis_source = hierarchical_synthesis_source(
            tuple(chunk_analyses),
            max_chars=self.settings.max_text_chars,
        )
        synthesis_run = await self._run_local_analysis(
            prompt=analysis_prompt(item, synthesis_source),
            session_id=f"{base_session}-synthesis-{len(chunks):03d}",
        )
        all_runs = tuple(chunk_runs) + (synthesis_run,)
        return _aggregate_hierarchical_run(all_runs, chunk_count=len(chunks))

    async def process_once(self, *, auto_enqueue: bool = False) -> int:
        if not self.settings.enabled:
            return 0
        if auto_enqueue:
            await self.repository.enqueue_pending(settings=self.settings)
        job = await self.repository.claim_next(self.worker_id)
        if job is None:
            return 0
        item: LibrarianObject | None = None
        try:
            item = await self.repository.load_object(job.storage_object_id)
            if item is None:
                raise TerminalStorageLibrarianError(
                    "Storage object исчез до анализа."
                )
            if item.storage_kind not in self.settings.allowed_kinds:
                raise UnsupportedStorageContent(
                    f"Категория {item.storage_kind} запрещена для Librarian."
                )
            source = await self.object_loader.download(
                item,
                max_bytes=self.settings.max_object_bytes,
            )
            source_text = extract_storage_text(
                item,
                source,
                settings=self.settings,
                allow_chunking=True,
            )
            run = await self._analyze_source(item, source_text)
            analysis = parse_librarian_analysis(run.output)
            await self.repository.complete(
                job=job,
                settings=self.settings,
                analysis=analysis,
                source_excerpt=source_text[:12000],
                run=run,
            )
            if self.report_publisher is not None:
                try:
                    await self.report_publisher.publish(item, analysis)
                except Exception as error:  # p2-approved-boundary: report-is-nonfatal
                    logger.warning(
                        "Storage Librarian report publication failed object_id=%s error=%s",
                        item.object_id,
                        redact_sensitive(str(error))[:1000],
                    )
            return 1
        except UnsupportedStorageContent as error:
            await self.repository.skip(
                job=job,
                settings=self.settings,
                reason=str(error),
            )
            return 1
        except TerminalStorageLibrarianError as error:
            terminal = await self.repository.fail(job, error, terminal=True)
            if terminal and self.report_publisher is not None:
                try:
                    await self.report_publisher.publish_failure(
                        object_id=job.storage_object_id,
                        item=item,
                        error=error,
                    )
                except Exception as publish_error:  # p2-approved-boundary: failure-report-is-nonfatal
                    logger.warning(
                        "Storage Librarian terminal failure publication failed "
                        "object_id=%s error=%s",
                        job.storage_object_id,
                        redact_sensitive(str(publish_error))[:1000],
                    )
            return 1
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary: isolate-storage-librarian-job
            terminal = await self.repository.fail(job, error)
            if terminal and self.report_publisher is not None:
                try:
                    await self.report_publisher.publish_failure(
                        object_id=job.storage_object_id,
                        item=item,
                        error=error,
                    )
                except Exception as publish_error:  # p2-approved-boundary: failure-report-is-nonfatal
                    logger.warning(
                        "Storage Librarian failure report publication failed object_id=%s error=%s",
                        job.storage_object_id,
                        redact_sensitive(str(publish_error))[:1000],
                    )
            return 1

    async def answer(self, question: str) -> str:
        if not self.settings.enabled:
            raise StorageLibrarianError("Storage Librarian выключен.")
        rows = await self.repository.search_analyses(question, limit=8)
        if not rows:
            recent = await self.repository.recent_analyses(days=365, limit=50)
            rows = _fallback_analysis_rows(question, recent, limit=8)
        if not rows:
            return "В проанализированном архиве совпадений пока нет."
        context: list[dict[str, object]] = []
        for row in rows:
            context.append(
                {
                    "storage_object_id": int(row["storage_object_id"]),
                    "kind": str(row["storage_kind"]),
                    "logical_key": str(row["logical_key"]),
                    "original_name": str(row["original_name"]),
                    "summary": str(row["summary"]),
                    "tags": _json_list(row["tags"]),
                    "entities": _json_list(row["entities"]),
                    "action_items": _json_list(row["action_items"]),
                    "analyzed_at": str(row["analyzed_at"]),
                }
            )
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]
        run = await self.answer_client.run(
            prompt=(
                "Ответь на вопрос владельца Velvet только по приведённым индексированным "
                "резюме. Сравни источники, явно отличай единичный сбой от повторяющейся "
                "проблемы, не используй внешние знания и не выдумывай отсутствующие факты. "
                "Для каждого важного утверждения укажи Storage ID.\n\n"
                f"Вопрос: {redact_sensitive(question)[:2000]}\n"
                f"Ключи поиска: {', '.join(_search_terms(question))}\n\n"
                "Контекст:\n"
                + json.dumps(context, ensure_ascii=False, indent=2)[:100000]
            ),
            session_id=f"velvet-storage-ask-{question_hash}-{stamp}",
            instructions=(
                "Ты локальный поисковый слой Telegram Storage Velvet. Отвечай по-русски, "
                "кратко, с указанием Storage ID и без вызова инструментов."
            ),
        )
        return run.output[:12000]


__all__ = (
    "LibrarianReportPublisher",
    "LibrarianRunClient",
    "StorageLibrarianService",
    "StorageObjectLoader",
)
