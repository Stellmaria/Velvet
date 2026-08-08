from __future__ import annotations

import io
import json
import os
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.application.storage_librarian import StorageLibrarianService
from velvet_bot.domains.telegram_storage.librarian_content import (
    chunk_analysis_source,
    chunk_source_char_limit,
    extract_storage_text,
    plan_storage_text_chunks,
)
from velvet_bot.domains.telegram_storage.librarian_models import (
    HermesRunResult,
    LibrarianJob,
    LibrarianObject,
    StorageLibrarianSettings,
    TerminalStorageLibrarianError,
)


def _settings(**overrides: object) -> StorageLibrarianSettings:
    values: dict[str, object] = {
        "enabled": True,
        "hermes_base_url": "http://hermes:8642",
        "hermes_api_key": "abcdefgh",
        "scan_interval_seconds": 60,
        "poll_interval_seconds": 2,
        "run_timeout_seconds": 420,
        "max_object_bytes": 12 * 1024 * 1024,
        "max_text_chars": 2000,
        "max_zip_entries": 40,
        "max_attempts": 3,
        "analyzer_version": "chunking:test",
        "allowed_kinds": ("diagnostics", "codex"),
        "text_context_length": 12288,
        "text_max_output_tokens": 768,
        "max_chunk_count": 4,
        "max_chunk_source_chars": 6000,
        "max_inference_calls": 5,
    }
    values.update(overrides)
    return StorageLibrarianSettings(**values)  # type: ignore[arg-type]


def _item(
    *,
    object_id: int = 39,
    name: str = "oversized.log",
    kind: str = "diagnostics",
    mime: str = "text/plain",
) -> LibrarianObject:
    return LibrarianObject(
        object_id=object_id,
        storage_kind=kind,
        logical_key=f"{kind}:chunking:{object_id}",
        original_name=name,
        mime_type=mime,
        size_bytes=0,
        sha256="a" * 64,
        encrypted=False,
        manifest={"source": "chunking-test"},
        parts=(),
    )


def _valid_run(*, analyzer: str = "ollama") -> HermesRunResult:
    output = json.dumps(
        {
            "summary": "Зафиксирован bounded local analysis без потери source slices.",
            "tags": ["diagnostics", "chunking"],
            "entities": [{"name": "Ollama", "type": "service"}],
            "action_items": [{"text": "Проверить итог", "priority": "medium"}],
            "sensitivity": "normal",
            "confidence": 90,
        },
        ensure_ascii=False,
    )
    return HermesRunResult(
        run_id=f"{analyzer}-run",
        output=output,
        usage={"prompt_tokens": 100, "completion_tokens": 50},
        analyzer=analyzer,
    )


def _repository(item: LibrarianObject) -> SimpleNamespace:
    return SimpleNamespace(
        enqueue_pending=AsyncMock(),
        claim_next=AsyncMock(return_value=LibrarianJob(1, item.object_id, 0, 3)),
        load_object=AsyncMock(return_value=item),
        complete=AsyncMock(),
        skip=AsyncMock(),
        fail=AsyncMock(return_value=True),
    )


class StorageLibrarianChunkSettingsTests(unittest.TestCase):
    def test_production_context_derives_bounded_chunk_defaults(self) -> None:
        env = {
            "STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH": "12288",
            "STORAGE_LIBRARIAN_TEXT_MAX_OUTPUT_TOKENS": "768",
            "STORAGE_LIBRARIAN_MAX_TEXT_CHARS": "120000",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = StorageLibrarianSettings.from_env()
        self.assertEqual(18_944, settings.max_text_chars)
        self.assertEqual(12, settings.max_chunk_count)
        self.assertEqual(220_000, settings.max_chunk_source_chars)
        self.assertEqual(13, settings.max_inference_calls)
        self.assertEqual(220_000, chunk_source_char_limit(settings))


class StorageLibrarianChunkPlanningTests(unittest.TestCase):
    def test_codex_zip_slightly_over_single_limit_is_not_truncated(self) -> None:
        settings = _settings()
        source_body = "A" * 2300 + "\nTAIL-SENTINEL"
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("report.txt", source_body)
        item = _item(name="codex-1c43fb8dd374.zip", kind="codex", mime="application/zip")

        source = extract_storage_text(
            item,
            archive_bytes.getvalue(),
            settings=settings,
            allow_chunking=True,
        )
        chunks = plan_storage_text_chunks(source, settings=settings)

        self.assertGreater(len(source), settings.max_text_chars)
        self.assertIn("TAIL-SENTINEL", source)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(source, "".join(chunks))

    def test_large_diagnostics_chunk_order_is_deterministic_and_bounded(self) -> None:
        settings = _settings(
            max_text_chars=18_944,
            max_chunk_count=12,
            max_chunk_source_chars=220_000,
            max_inference_calls=13,
        )
        source = "".join(f"{index:06d}: diagnostic line\n" for index in range(8000))
        self.assertGreater(len(source), settings.max_text_chars)
        self.assertLess(len(source), 220_000)

        first = plan_storage_text_chunks(source, settings=settings)
        second = plan_storage_text_chunks(source, settings=settings)

        self.assertEqual(first, second)
        self.assertEqual(source, "".join(first))
        self.assertLessEqual(len(first), settings.max_chunk_count)
        for index, chunk in enumerate(first, start=1):
            wrapped = chunk_analysis_source(
                chunk,
                index=index,
                total=len(first),
                max_chars=settings.max_text_chars,
            )
            self.assertLessEqual(len(wrapped), settings.max_text_chars)

    def test_hard_cap_rejects_multimegabyte_plan_without_partial_source(self) -> None:
        settings = _settings(
            max_text_chars=18_944,
            max_chunk_count=12,
            max_chunk_source_chars=220_000,
            max_inference_calls=13,
        )
        source = "x" * 3_932_555
        with self.assertRaisesRegex(TerminalStorageLibrarianError, "hard bounded chunk-plan"):
            plan_storage_text_chunks(source, settings=settings)


class StorageLibrarianHierarchicalServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_chunked_object_uses_sequential_local_ollama_then_synthesis(self) -> None:
        settings = _settings()
        item = _item()
        payload = ("line=timeout\n" * 220).encode("utf-8")
        source = extract_storage_text(
            item,
            payload,
            settings=settings,
            allow_chunking=True,
        )
        chunks = plan_storage_text_chunks(source, settings=settings)
        self.assertGreater(len(chunks), 1)
        expected_calls = len(chunks) + 1

        analysis_client = SimpleNamespace(run=AsyncMock(return_value=_valid_run()))
        answer_client = SimpleNamespace(run=AsyncMock())
        service = StorageLibrarianService(
            database=object(),  # type: ignore[arg-type]
            settings=settings,
            object_loader=SimpleNamespace(download=AsyncMock(return_value=payload)),
            analysis_client=analysis_client,
            answer_client=answer_client,
        )
        service.repository = _repository(item)

        self.assertEqual(1, await service.process_once())
        self.assertEqual(expected_calls, analysis_client.run.await_count)
        answer_client.run.assert_not_awaited()
        service.repository.complete.assert_awaited_once()
        service.repository.fail.assert_not_awaited()

        sessions = [
            call.kwargs["session_id"] for call in analysis_client.run.await_args_list
        ]
        self.assertTrue(all("chunk-" in value for value in sessions[:-1]))
        self.assertIn("synthesis", sessions[-1])
        completed_run = service.repository.complete.await_args.kwargs["run"]
        self.assertEqual("ollama", completed_run.analyzer)
        self.assertTrue(completed_run.usage["hierarchical"])
        self.assertEqual(len(chunks), completed_run.usage["chunk_count"])
        self.assertEqual(expected_calls, completed_run.usage["inference_calls"])
        self.assertEqual(100 * expected_calls, completed_run.usage["prompt_tokens"])
        self.assertEqual(50 * expected_calls, completed_run.usage["completion_tokens"])

    async def test_inference_budget_rejects_before_any_model_call(self) -> None:
        settings = _settings(max_inference_calls=2)
        item = _item(object_id=41)
        payload = ("diagnostic\n" * 260).encode("utf-8")
        analysis_client = SimpleNamespace(run=AsyncMock(return_value=_valid_run()))
        service = StorageLibrarianService(
            database=object(),  # type: ignore[arg-type]
            settings=settings,
            object_loader=SimpleNamespace(download=AsyncMock(return_value=payload)),
            analysis_client=analysis_client,
            answer_client=SimpleNamespace(run=AsyncMock()),
        )
        service.repository = _repository(item)

        self.assertEqual(1, await service.process_once())
        analysis_client.run.assert_not_awaited()
        service.repository.complete.assert_not_awaited()
        service.repository.fail.assert_awaited_once()
        self.assertTrue(service.repository.fail.await_args.kwargs["terminal"])
        self.assertIn(
            "inference budget",
            str(service.repository.fail.await_args.args[1]),
        )

    async def test_non_ollama_analyzer_is_terminal_without_fallback(self) -> None:
        settings = _settings()
        item = _item(object_id=42)
        payload = ("diagnostic\n" * 260).encode("utf-8")
        analysis_client = SimpleNamespace(
            run=AsyncMock(return_value=_valid_run(analyzer="hermes"))
        )
        answer_client = SimpleNamespace(run=AsyncMock())
        service = StorageLibrarianService(
            database=object(),  # type: ignore[arg-type]
            settings=settings,
            object_loader=SimpleNamespace(download=AsyncMock(return_value=payload)),
            analysis_client=analysis_client,
            answer_client=answer_client,
        )
        service.repository = _repository(item)

        self.assertEqual(1, await service.process_once())
        self.assertEqual(1, analysis_client.run.await_count)
        answer_client.run.assert_not_awaited()
        service.repository.complete.assert_not_awaited()
        service.repository.fail.assert_awaited_once()
        self.assertTrue(service.repository.fail.await_args.kwargs["terminal"])
        self.assertIn(
            "local Ollama only",
            str(service.repository.fail.await_args.args[1]),
        )


if __name__ == "__main__":
    unittest.main()
