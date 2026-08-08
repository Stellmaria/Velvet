from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from velvet_bot.domains.telegram_storage.librarian_models import (
    StorageLibrarianSettings,
    TerminalStorageLibrarianError,
)
from velvet_bot.infrastructure.ai.storage_librarian_ollama import (
    STORAGE_LIBRARIAN_ANALYSIS_SCHEMA,
    OllamaStorageAnalysisClient,
)


def _settings() -> StorageLibrarianSettings:
    with patch.dict(os.environ, {}, clear=True):
        return StorageLibrarianSettings.from_env()


def _analysis() -> dict[str, object]:
    return {
        "summary": "Краткий итог.",
        "tags": ["diagnostics"],
        "entities": [{"name": "Ollama", "type": "service"}],
        "action_items": [{"text": "Проверить лог", "priority": "high"}],
        "sensitivity": "normal",
        "confidence": 91,
    }


def _payload(
    *,
    done_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, object]:
    content = (
        json.dumps(_analysis(), ensure_ascii=False)
        if done_reason == "stop"
        else "{"
    )
    return {
        "done": True,
        "done_reason": done_reason,
        "message": {"content": content},
        "prompt_eval_count": prompt_tokens,
        "eval_count": completion_tokens,
    }


class _Response:
    status = 200

    def __init__(self, payload: object) -> None:
        self.payload = payload

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def json(self, *, content_type: object = None) -> object:
        del content_type
        return self.payload


class _Session:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = list(payloads)
        self.requests: list[dict[str, object]] = []

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def post(self, url: str, *, json: dict[str, object]) -> _Response:
        self.requests.append({"url": url, "json": json})
        return _Response(self.payloads.pop(0))


class _SessionFactory:
    def __init__(self, sequences: list[list[object]]) -> None:
        self.sequences = list(sequences)
        self.sessions: list[_Session] = []

    def __call__(self, **kwargs: object) -> _Session:
        del kwargs
        session = _Session(self.sequences.pop(0))
        self.sessions.append(session)
        return session


class StorageLibrarianLengthRetryTests(unittest.IsolatedAsyncioTestCase):
    def test_schema_caps_verbose_fields(self) -> None:
        properties = STORAGE_LIBRARIAN_ANALYSIS_SCHEMA["properties"]
        assert isinstance(properties, dict)
        summary = properties["summary"]
        tags = properties["tags"]
        entities = properties["entities"]
        actions = properties["action_items"]
        assert isinstance(summary, dict)
        assert isinstance(tags, dict)
        assert isinstance(entities, dict)
        assert isinstance(actions, dict)
        self.assertEqual(400, summary["maxLength"])
        self.assertEqual(3, tags["maxItems"])
        self.assertEqual(3, entities["maxItems"])
        self.assertEqual(3, actions["maxItems"])

    async def test_single_shot_length_retries_once_with_larger_output_budget(
        self,
    ) -> None:
        factory = _SessionFactory(
            [[
                _payload(
                    done_reason="length",
                    prompt_tokens=21,
                    completion_tokens=384,
                ),
                _payload(
                    done_reason="stop",
                    prompt_tokens=21,
                    completion_tokens=88,
                ),
            ]]
        )
        client = OllamaStorageAnalysisClient(
            _settings(),
            session_factory=factory,
        )

        result = await client.run(
            prompt="short diagnostic",
            session_id="velvet-storage-35-test",
            instructions="strict",
        )

        session = factory.sessions[0]
        self.assertEqual(2, len(session.requests))
        first = session.requests[0]["json"]
        second = session.requests[1]["json"]
        assert isinstance(first, dict)
        assert isinstance(second, dict)
        first_options = first["options"]
        second_options = second["options"]
        assert isinstance(first_options, dict)
        assert isinstance(second_options, dict)
        self.assertEqual(384, first_options["num_predict"])
        self.assertEqual(768, second_options["num_predict"])
        self.assertEqual(42, result.usage["prompt_tokens"])
        self.assertEqual(472, result.usage["completion_tokens"])
        self.assertEqual(2, result.usage["inference_calls"])
        self.assertEqual(1, result.usage["length_retries"])
        self.assertEqual(2, result.usage["actual_inference_calls"])
        self.assertEqual(1, result.usage["object_length_retries"])

    async def test_retry_never_steals_context_from_a_near_limit_prompt(self) -> None:
        factory = _SessionFactory(
            [[
                _payload(
                    done_reason="length",
                    prompt_tokens=100,
                    completion_tokens=384,
                ),
                _payload(
                    done_reason="stop",
                    prompt_tokens=100,
                    completion_tokens=120,
                ),
            ]]
        )
        client = OllamaStorageAnalysisClient(
            _settings(),
            session_factory=factory,
        )

        result = await client.run(
            prompt="x" * 12480,
            session_id="velvet-storage-36-test",
            instructions="strict",
        )

        requests = factory.sessions[0].requests
        second = requests[1]["json"]
        assert isinstance(second, dict)
        options = second["options"]
        assert isinstance(options, dict)
        self.assertEqual(384, options["num_predict"])
        self.assertEqual(384, result.usage["retry_num_predict"])

    async def test_second_length_is_terminal_and_never_gets_a_third_call(self) -> None:
        factory = _SessionFactory(
            [[
                _payload(
                    done_reason="length",
                    prompt_tokens=10,
                    completion_tokens=384,
                ),
                _payload(
                    done_reason="length",
                    prompt_tokens=10,
                    completion_tokens=768,
                ),
            ]]
        )
        client = OllamaStorageAnalysisClient(
            _settings(),
            session_factory=factory,
        )

        with self.assertRaisesRegex(
            TerminalStorageLibrarianError,
            "done_reason=length",
        ):
            await client.run(
                prompt="short",
                session_id="velvet-storage-37-test",
                instructions="strict",
            )

        self.assertEqual(2, len(factory.sessions[0].requests))

    async def test_full_hierarchical_plan_does_not_exceed_inference_cap(self) -> None:
        settings = replace(_settings(), max_inference_calls=3)
        factory = _SessionFactory(
            [[
                _payload(
                    done_reason="length",
                    prompt_tokens=10,
                    completion_tokens=384,
                )
            ]]
        )
        client = OllamaStorageAnalysisClient(
            settings,
            session_factory=factory,
        )

        with self.assertRaisesRegex(
            TerminalStorageLibrarianError,
            "done_reason=length",
        ):
            await client.run(
                prompt="chunk",
                session_id="velvet-storage-38-test-chunk-001-of-002",
                instructions="strict",
            )

        self.assertEqual(1, len(factory.sessions[0].requests))

    async def test_hierarchical_retry_budget_is_shared_until_synthesis(self) -> None:
        settings = replace(_settings(), max_inference_calls=4)
        factory = _SessionFactory(
            [
                [
                    _payload(
                        done_reason="length",
                        prompt_tokens=10,
                        completion_tokens=384,
                    ),
                    _payload(
                        done_reason="stop",
                        prompt_tokens=10,
                        completion_tokens=80,
                    ),
                ],
                [
                    _payload(
                        done_reason="stop",
                        prompt_tokens=10,
                        completion_tokens=70,
                    )
                ],
                [
                    _payload(
                        done_reason="stop",
                        prompt_tokens=10,
                        completion_tokens=60,
                    )
                ],
            ]
        )
        client = OllamaStorageAnalysisClient(
            settings,
            session_factory=factory,
        )

        await client.run(
            prompt="chunk one",
            session_id="velvet-storage-39-test-chunk-001-of-002",
            instructions="strict",
        )
        await client.run(
            prompt="chunk two",
            session_id="velvet-storage-39-test-chunk-002-of-002",
            instructions="strict",
        )
        synthesis = await client.run(
            prompt="synthesis",
            session_id="velvet-storage-39-test-synthesis-002",
            instructions="strict",
        )

        self.assertEqual(2, len(factory.sessions[0].requests))
        self.assertEqual(1, len(factory.sessions[1].requests))
        self.assertEqual(1, len(factory.sessions[2].requests))
        self.assertEqual(4, synthesis.usage["actual_inference_calls"])
        self.assertEqual(1, synthesis.usage["object_length_retries"])


if __name__ == "__main__":
    unittest.main()
