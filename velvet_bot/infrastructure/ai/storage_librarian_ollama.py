from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from typing import AsyncContextManager, Protocol, cast

import aiohttp

from velvet_bot.domains.telegram_storage.librarian_models import (
    HermesRunResult,
    JsonObject,
    StorageLibrarianError,
    StorageLibrarianSettings,
    TerminalStorageLibrarianError,
    storage_librarian_text_prompt_char_limit,
)

STORAGE_LIBRARIAN_ANALYSIS_SCHEMA: JsonObject = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary",
        "tags",
        "entities",
        "action_items",
        "sensitivity",
        "confidence",
    ],
    "properties": {
        "summary": {"type": "string"},
        "tags": {
            "type": "array",
            "maxItems": 6,
            "items": {"type": "string"},
        },
        "entities": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "type"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                },
            },
        },
        "action_items": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "priority"],
                "properties": {
                    "text": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
            },
        },
        "sensitivity": {
            "type": "string",
            "enum": ["normal", "sensitive", "restricted"],
        },
        "confidence": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": (
                "Уверенность в выводах по предоставленному источнику, не severity. "
                "Однозначный diagnostic log допускает high confidence."
            ),
        },
    },
}


class _ResponseProtocol(Protocol):
    status: int

    async def json(self, *, content_type: object = None) -> object: ...


class _SessionProtocol(Protocol):
    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
    ) -> AsyncContextManager[_ResponseProtocol]: ...


def _terminal(message: str) -> TerminalStorageLibrarianError:
    return TerminalStorageLibrarianError(message)


def _require_string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise _terminal(f"Ollama schema mismatch: {path} должен быть string.")
    return value


def _validate_analysis(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise _terminal("Ollama schema mismatch: ответ должен быть object.")
    required = {
        "summary", "tags", "entities", "action_items", "sensitivity", "confidence"
    }
    if set(value) != required:
        raise _terminal("Ollama schema mismatch: неверный набор полей.")
    _require_string(value["summary"], "summary")
    tags = value["tags"]
    if not isinstance(tags, list) or len(tags) > 6:
        raise _terminal("Ollama schema mismatch: tags должен содержать до 6 элементов.")
    for tag in tags:
        _require_string(tag, "tags[]")
    entities = value["entities"]
    if not isinstance(entities, list) or len(entities) > 6:
        raise _terminal("Ollama schema mismatch: entities должен содержать до 6 элементов.")
    for entity in entities:
        if not isinstance(entity, dict) or set(entity) != {"name", "type"}:
            raise _terminal("Ollama schema mismatch: неверная entity.")
        _require_string(entity["name"], "entities[].name")
        _require_string(entity["type"], "entities[].type")
    actions = value["action_items"]
    if not isinstance(actions, list) or len(actions) > 6:
        raise _terminal(
            "Ollama schema mismatch: action_items должен содержать до 6 элементов."
        )
    for action in actions:
        if not isinstance(action, dict) or set(action) != {"text", "priority"}:
            raise _terminal("Ollama schema mismatch: неверный action_item.")
        _require_string(action["text"], "action_items[].text")
        priority = action["priority"]
        if not isinstance(priority, str) or priority not in {"low", "medium", "high"}:
            raise _terminal("Ollama schema mismatch: неверный priority.")
    sensitivity = value["sensitivity"]
    if not isinstance(sensitivity, str) or sensitivity not in {
        "normal", "sensitive", "restricted"
    }:
        raise _terminal("Ollama schema mismatch: неверный sensitivity.")
    confidence = value["confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, int)
        or not 0 <= confidence <= 100
    ):
        raise _terminal("Ollama schema mismatch: confidence должен быть integer 0..100.")
    return cast(JsonObject, value)


def _usage_count(payload: dict[object, object], name: str) -> int:
    value = payload.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _terminal(f"Ollama analysis usage field {name} is invalid.")
    return value


def _max_prompt_chars(settings: StorageLibrarianSettings) -> int:
    try:
        return storage_librarian_text_prompt_char_limit(
            context_length=settings.text_context_length,
            max_output_tokens=settings.text_max_output_tokens,
        )
    except ValueError as error:
        raise _terminal(
            "Ollama analysis configuration leaves insufficient input context."
        ) from error


class OllamaStorageAnalysisClient:
    def __init__(
        self,
        settings: StorageLibrarianSettings,
        *,
        session_factory: Callable[..., AsyncContextManager[_SessionProtocol]] = cast(
            Callable[..., AsyncContextManager[_SessionProtocol]],
            aiohttp.ClientSession,
        ),
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def run(
        self,
        *,
        prompt: str,
        session_id: str,
        instructions: str,
    ) -> HermesRunResult:
        prompt_chars = len(prompt) + len(instructions) + 512
        max_prompt_chars = _max_prompt_chars(self._settings)
        if prompt_chars > max_prompt_chars:
            raise _terminal(
                "Ollama analysis input exceeds the bounded text context: "
                f"chars={prompt_chars}, limit={max_prompt_chars}. "
                "Chunking is not implemented; silent truncation is forbidden."
            )

        request: dict[str, object] = {
            "model": self._settings.text_model,
            "stream": False,
            "think": False,
            "keep_alive": self._settings.ollama_keep_alive,
            "format": STORAGE_LIBRARIAN_ANALYSIS_SCHEMA,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "num_ctx": self._settings.text_context_length,
                "num_predict": self._settings.text_max_output_tokens,
                "temperature": 0,
                "top_k": 20,
                "top_p": 0.9,
                "repeat_penalty": 1.05,
                "seed": 42,
            },
        }
        timeout = aiohttp.ClientTimeout(total=self._settings.run_timeout_seconds)
        try:
            async with self._session_factory(timeout=timeout) as session:
                async with session.post(
                    self._settings.ollama_base_url + "/api/chat",
                    json=request,
                ) as response:
                    if response.status < 200 or response.status >= 300:
                        error_type = (
                            StorageLibrarianError
                            if response.status in {408, 429} or response.status >= 500
                            else TerminalStorageLibrarianError
                        )
                        raise error_type(f"Ollama analysis HTTP {response.status}.")
                    try:
                        payload = await response.json(content_type=None)
                    except (json.JSONDecodeError, ValueError, TypeError) as error:
                        raise _terminal(
                            "Ollama analysis вернул malformed HTTP JSON."
                        ) from error
        except StorageLibrarianError:
            raise
        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as error:
            raise StorageLibrarianError("Ollama analysis timeout.") from error
        except aiohttp.ClientError as error:
            raise StorageLibrarianError(
                f"Ollama analysis network error: {type(error).__name__}."
            ) from error

        if not isinstance(payload, dict):
            raise _terminal("Ollama analysis вернул malformed response.")
        if payload.get("done") is not True or payload.get("done_reason") != "stop":
            reason = payload.get("done_reason")
            safe_reason = reason if isinstance(reason, str) else type(reason).__name__
            raise _terminal(
                "Ollama analysis did not complete normally: "
                f"done_reason={safe_reason}."
            )
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise _terminal("Ollama analysis не вернул message.content.")
        try:
            decoded: object = json.loads(content)
        except json.JSONDecodeError as error:
            raise _terminal("Ollama analysis вернул invalid JSON content.") from error
        analysis = _validate_analysis(decoded)
        fingerprint = hashlib.sha256(
            f"{session_id}\0{self._settings.text_model}".encode("utf-8")
        ).hexdigest()[:24]
        usage: JsonObject = {
            "prompt_tokens": _usage_count(payload, "prompt_eval_count"),
            "completion_tokens": _usage_count(payload, "eval_count"),
        }
        return HermesRunResult(
            run_id=f"ollama-storage-{fingerprint}",
            output=json.dumps(analysis, ensure_ascii=False, separators=(",", ":")),
            usage=usage,
            analyzer="ollama",
        )


__all__ = (
    "OllamaStorageAnalysisClient",
    "STORAGE_LIBRARIAN_ANALYSIS_SCHEMA",
)
