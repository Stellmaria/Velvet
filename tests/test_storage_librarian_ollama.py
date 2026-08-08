from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

from velvet_bot.application.storage_librarian import StorageLibrarianService
from velvet_bot.domains.telegram_storage.librarian_content import analysis_prompt
from velvet_bot.domains.telegram_storage.librarian_models import (
    HermesRunResult,
    LibrarianJob,
    LibrarianObject,
    StorageLibrarianError,
    StorageLibrarianSettings,
    TerminalStorageLibrarianError,
)
from velvet_bot.infrastructure.ai.storage_librarian_ollama import (
    STORAGE_LIBRARIAN_ANALYSIS_SCHEMA,
    OllamaStorageAnalysisClient,
)


def _settings() -> StorageLibrarianSettings:
    return StorageLibrarianSettings.from_env()


def _valid_analysis() -> dict[str, object]:
    return {
        "summary": "Короткий diagnostic log фиксирует однозначный timeout.",
        "tags": ["diagnostics", "timeout"],
        "entities": [{"name": "Ollama", "type": "service"}],
        "action_items": [{"text": "Проверить сеть", "priority": "high"}],
        "sensitivity": "normal",
        "confidence": 92,
    }


def _ollama_payload(
    *,
    content: str | None = None,
    done: bool = True,
    done_reason: str = "stop",
    **extra: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "done": done,
        "done_reason": done_reason,
        "message": {"content": content if content is not None else json.dumps(_valid_analysis())},
    }
    payload.update(extra)
    return payload


class _Response:
    def __init__(self, *, status: int = 200, payload: object = None) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def json(self, *, content_type: object = None) -> object:
        del content_type
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload

    async def text(self) -> str:
        return "upstream response omitted"


class _Session:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response
        self.request: dict[str, object] | None = None

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def post(self, url: str, *, json: dict[str, object]) -> _Response:
        self.request = {"url": url, "json": json}
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class StorageLibrarianSettingsRegressionTests(unittest.TestCase):
    def test_new_defaults_and_manual_first_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = _settings()
        self.assertEqual("http://ollama-librarian:11434", settings.ollama_base_url)
        self.assertEqual("velvet-librarian-text:v1", settings.text_model)
        self.assertEqual("velvet-librarian-vision:v1", settings.vision_model)
        self.assertEqual(8192, settings.text_context_length)
        self.assertEqual(384, settings.text_max_output_tokens)
        self.assertEqual(16384, settings.vision_context_length)
        self.assertEqual(640, settings.vision_max_output_tokens)
        self.assertEqual("5m", settings.ollama_keep_alive)
        self.assertEqual(720, settings.run_timeout_seconds)
        self.assertEqual("velvet-librarian:qwen3-4b-text:v4", settings.analyzer_version)
        self.assertNotEqual("true", os.getenv("STORAGE_LIBRARIAN_AUTO_ENQUEUE", "false"))

    def test_new_environment_overrides(self) -> None:
        env = {
            "STORAGE_LIBRARIAN_OLLAMA_BASE_URL": "http://private-ollama:9999/",
            "STORAGE_LIBRARIAN_TEXT_MODEL": "text:test",
            "STORAGE_LIBRARIAN_VISION_MODEL": "vision:test",
            "STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH": "4096",
            "STORAGE_LIBRARIAN_TEXT_MAX_OUTPUT_TOKENS": "256",
            "STORAGE_LIBRARIAN_VISION_CONTEXT_LENGTH": "12288",
            "STORAGE_LIBRARIAN_VISION_MAX_OUTPUT_TOKENS": "512",
            "STORAGE_LIBRARIAN_OLLAMA_KEEP_ALIVE": "2m",
            "STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS": "75",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = _settings()
        self.assertEqual("http://private-ollama:9999", settings.ollama_base_url)
        self.assertEqual("text:test", settings.text_model)
        self.assertEqual("vision:test", settings.vision_model)
        self.assertEqual(4096, settings.text_context_length)
        self.assertEqual(256, settings.text_max_output_tokens)
        self.assertEqual(12288, settings.vision_context_length)
        self.assertEqual(512, settings.vision_max_output_tokens)
        self.assertEqual("2m", settings.ollama_keep_alive)
        self.assertEqual(720, settings.run_timeout_seconds)

    def test_run_timeout_can_be_raised_above_cpu_floor(self) -> None:
        with patch.dict(
            os.environ,
            {"STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS": "900"},
            clear=True,
        ):
            settings = _settings()
        self.assertEqual(900, settings.run_timeout_seconds)


class OllamaStorageAnalysisClientTests(unittest.IsolatedAsyncioTestCase):
    async def _run(
        self,
        response: _Response | BaseException,
        *,
        prompt: str = "short diagnostic",
    ):
        session = _Session(response)
        client = OllamaStorageAnalysisClient(_settings(), session_factory=lambda **_: session)
        result = await client.run(
            prompt=prompt,
            session_id="storage-7",
            instructions="strict",
        )
        return result, session

    async def test_request_is_bounded_non_thinking_and_strict(self) -> None:
        payload = _ollama_payload(prompt_eval_count=28, eval_count=61)
        result, session = await self._run(_Response(payload=payload))
        request = session.request
        assert request is not None
        body = request["json"]
        assert isinstance(body, dict)
        self.assertEqual("http://ollama-librarian:11434/api/chat", request["url"])
        self.assertEqual("velvet-librarian-text:v1", body["model"])
        self.assertFalse(body["think"])
        self.assertEqual(STORAGE_LIBRARIAN_ANALYSIS_SCHEMA, body["format"])
        self.assertEqual("5m", body["keep_alive"])
        self.assertEqual(
            {
                "num_ctx": 8192,
                "num_predict": 384,
                "temperature": 0,
                "top_k": 20,
                "top_p": 0.9,
                "repeat_penalty": 1.05,
                "seed": 42,
            },
            body["options"],
        )
        self.assertTrue(result.run_id.startswith("ollama-storage-"))
        self.assertEqual("ollama", result.analyzer)
        self.assertEqual(28, result.usage["prompt_tokens"])
        self.assertNotIn("short diagnostic", result.run_id)

    async def test_valid_response_maps_and_diagnostic_confidence_is_meaningful(self) -> None:
        result, _ = await self._run(_Response(payload=_ollama_payload()))
        decoded = json.loads(result.output)
        self.assertIn("timeout", decoded["summary"])
        self.assertTrue(decoded["tags"])
        self.assertGreater(decoded["confidence"], 0)

    async def test_non_stop_completion_is_terminal(self) -> None:
        with self.assertRaisesRegex(TerminalStorageLibrarianError, "done_reason=length"):
            await self._run(_Response(payload=_ollama_payload(done_reason="length")))

    async def test_missing_done_flag_is_terminal(self) -> None:
        payload = _ollama_payload()
        payload.pop("done")
        with self.assertRaisesRegex(TerminalStorageLibrarianError, "did not complete"):
            await self._run(_Response(payload=payload))

    async def test_oversized_prompt_fails_closed_before_http(self) -> None:
        session = _Session(_Response(payload=_ollama_payload()))
        client = OllamaStorageAnalysisClient(_settings(), session_factory=lambda **_: session)
        with self.assertRaisesRegex(TerminalStorageLibrarianError, "silent truncation"):
            await client.run(
                prompt="я" * 20000,
                session_id="storage-large",
                instructions="strict",
            )
        self.assertIsNone(session.request)

    async def test_timeout_and_network_errors_are_controlled(self) -> None:
        for error in (asyncio.TimeoutError(), aiohttp.ClientConnectionError("offline")):
            with self.subTest(error=type(error).__name__):
                with self.assertRaisesRegex(StorageLibrarianError, "Ollama"):
                    await self._run(error)

    async def test_http_error_is_controlled_without_body_leak(self) -> None:
        with self.assertRaisesRegex(StorageLibrarianError, "HTTP 503") as raised:
            await self._run(_Response(status=503, payload={"secret": "must-not-leak"}))
        self.assertNotIn("must-not-leak", str(raised.exception))
        with self.assertRaises(TerminalStorageLibrarianError):
            await self._run(_Response(status=400, payload={}))

    async def test_invalid_json_and_incomplete_schema_are_terminal(self) -> None:
        cases = (
            _ollama_payload(content="not json"),
            _ollama_payload(content=json.dumps({"summary": "only"})),
            {"done": True, "done_reason": "stop", "message": {}},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(TerminalStorageLibrarianError):
                    await self._run(_Response(payload=payload))

    async def test_unhashable_enum_values_are_controlled_schema_errors(self) -> None:
        for field, invalid in (
            ("sensitivity", {}),
            ("action_items", [{"text": "x", "priority": []}]),
        ):
            analysis = _valid_analysis()
            analysis[field] = invalid
            with self.subTest(field=field):
                with self.assertRaisesRegex(TerminalStorageLibrarianError, "schema mismatch"):
                    await self._run(
                        _Response(payload=_ollama_payload(content=json.dumps(analysis)))
                    )

    async def test_malformed_usage_is_a_terminal_error(self) -> None:
        with self.assertRaisesRegex(TerminalStorageLibrarianError, "usage"):
            await self._run(
                _Response(payload=_ollama_payload(prompt_eval_count="not-an-integer"))
            )


class StorageLibrarianPromptTests(unittest.TestCase):
    def test_prompt_requires_russian_and_does_not_anchor_confidence_to_zero(self) -> None:
        item = LibrarianObject(
            7,
            "diagnostics",
            "diag:7",
            "short.log",
            "text/plain",
            8,
            "a" * 64,
            False,
            {},
            (),
        )
        prompt = analysis_prompt(item, "status=ok")
        self.assertIn("пиши по-русски", prompt)
        self.assertIn("уверенность в выводах", prompt)
        self.assertIn("технические имена", prompt)
        self.assertNotIn('"confidence": 0', prompt)


class StorageLibrarianStartScriptTests(unittest.TestCase):
    def test_start_script_honors_aliases_and_skips_existing_source_pulls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root.parent) as directory:
            temp = Path(directory)
            env_file = temp / "librarian.env"
            env_file.write_text(
                "STORAGE_LIBRARIAN_TEXT_MODEL=text:override\n"
                "STORAGE_LIBRARIAN_VISION_MODEL=vision:override\n",
                encoding="utf-8",
            )
            log = temp / "docker.log"
            docker = temp / "docker"
            docker.write_text(
                "#!/usr/bin/env sh\n"
                "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            docker.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{temp}:{os.environ['PATH']}",
                "VELVET_ENV_FILE": str(env_file),
                "LIBRARIAN_COMPOSE_FILE": str(root / "deploy/hermes-librarian/compose.yaml"),
                "FAKE_DOCKER_LOG": str(log),
            }
            subprocess.run(
                ["bash", str(root / "deploy/hermes-librarian/start.sh")],
                check=True,
                env=env,
                timeout=10,
            )
            commands = log.read_text(encoding="utf-8")
        self.assertIn("ollama create text:override", commands)
        self.assertIn("ollama create vision:override", commands)
        self.assertIn("ollama show text:override", commands)
        self.assertIn("ollama show vision:override", commands)
        self.assertNotIn("ollama pull", commands)


class StorageLibrarianClientSplitTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_once_uses_analysis_client_and_answer_uses_hermes(self) -> None:
        analysis_client = SimpleNamespace(
            run=AsyncMock(
                return_value=HermesRunResult(
                    run_id="ollama-storage-safe",
                    output=json.dumps(_valid_analysis()),
                    usage={},
                    analyzer="ollama",
                )
            )
        )
        answer_client = SimpleNamespace(
            run=AsyncMock(return_value=HermesRunResult("hermes-run", "Ответ", {}))
        )
        loader = SimpleNamespace(download=AsyncMock(return_value=b"timeout\n"))
        service = StorageLibrarianService(
            database=object(),  # type: ignore[arg-type]
            settings=_settings(),
            object_loader=loader,
            analysis_client=analysis_client,
            answer_client=answer_client,
        )
        service.repository = SimpleNamespace(
            enqueue_pending=AsyncMock(),
            claim_next=AsyncMock(return_value=LibrarianJob(1, 7, 0, 3)),
            load_object=AsyncMock(
                return_value=LibrarianObject(
                    7,
                    "diagnostics",
                    "diag:7",
                    "short.log",
                    "text/plain",
                    8,
                    "a" * 64,
                    False,
                    {},
                    (),
                )
            ),
            complete=AsyncMock(),
            skip=AsyncMock(),
            fail=AsyncMock(),
            search_analyses=AsyncMock(
                return_value=[
                    {
                        "storage_object_id": 7,
                        "storage_kind": "diagnostics",
                        "logical_key": "diag:7",
                        "original_name": "short.log",
                        "summary": "timeout",
                        "tags": [],
                        "entities": [],
                        "action_items": [],
                        "analyzed_at": "2026-08-04T00:00:00Z",
                    }
                ]
            ),
        )
        object.__setattr__(service.settings, "enabled", True)

        self.assertEqual(1, await service.process_once())
        self.assertEqual("Ответ", await service.answer("Что сломалось?"))
        analysis_client.run.assert_awaited_once()
        answer_client.run.assert_awaited_once()

    async def test_terminal_analysis_error_is_not_retried(self) -> None:
        analysis_client = SimpleNamespace(
            run=AsyncMock(side_effect=TerminalStorageLibrarianError("invalid schema"))
        )
        service = StorageLibrarianService(
            database=object(),  # type: ignore[arg-type]
            settings=_settings(),
            object_loader=SimpleNamespace(download=AsyncMock(return_value=b"x")),
            analysis_client=analysis_client,
            answer_client=SimpleNamespace(run=AsyncMock()),
        )
        service.repository = SimpleNamespace(
            enqueue_pending=AsyncMock(),
            claim_next=AsyncMock(return_value=LibrarianJob(1, 7, 1, 3)),
            load_object=AsyncMock(
                return_value=LibrarianObject(
                    7,
                    "diagnostics",
                    "diag:7",
                    "short.log",
                    "text/plain",
                    1,
                    "a" * 64,
                    False,
                    {},
                    (),
                )
            ),
            complete=AsyncMock(),
            skip=AsyncMock(),
            fail=AsyncMock(return_value=True),
        )
        object.__setattr__(service.settings, "enabled", True)

        self.assertEqual(1, await service.process_once())
        service.repository.fail.assert_awaited_once()
        self.assertTrue(service.repository.fail.await_args.kwargs["terminal"])


if __name__ == "__main__":
    unittest.main()