from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Sequence


class RoleplayProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RoleplayGenerationOptions:
    num_ctx: int = 8192
    max_output_tokens: int = 900
    temperature: float = 0.9
    top_p: float = 0.92
    min_p: float = 0.05
    repeat_penalty: float = 1.08

    def __post_init__(self) -> None:
        if not 2048 <= self.num_ctx <= 32_768:
            raise ValueError("num_ctx должен быть от 2048 до 32768.")
        if not 128 <= self.max_output_tokens < self.num_ctx:
            raise ValueError("max_output_tokens должен быть от 128 и меньше num_ctx.")
        for name, value, minimum, maximum in (
            ("temperature", self.temperature, 0.0, 2.0),
            ("top_p", self.top_p, 0.01, 1.0),
            ("min_p", self.min_p, 0.0, 1.0),
            ("repeat_penalty", self.repeat_penalty, 0.8, 2.0),
        ):
            if not minimum <= float(value) <= maximum:
                raise ValueError(f"{name} должен быть от {minimum} до {maximum}.")


class OllamaRoleplayClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: int = 600,
        keep_alive: str | int = "30m",
    ) -> None:
        cleaned_url = base_url.strip().rstrip("/")
        cleaned_model = model.strip()
        if not cleaned_url:
            raise ValueError("Ollama base_url не может быть пустым.")
        if not cleaned_model:
            raise ValueError("Ollama RP model не может быть пустой.")
        self.base_url = cleaned_url
        self.model = cleaned_model
        self.timeout_seconds = max(30, min(int(timeout_seconds), 3600))
        self.keep_alive = keep_alive

    def request_body(
        self,
        messages: Sequence[dict[str, str]],
        options: RoleplayGenerationOptions,
    ) -> dict[str, Any]:
        cleaned_messages: list[dict[str, str]] = []
        for message in messages:
            role = str(message.get("role") or "").strip()
            content = str(message.get("content") or "").strip()
            if role not in {"system", "user", "assistant"} or not content:
                raise ValueError("Некорректное сообщение для Ollama RP.")
            cleaned_messages.append({"role": role, "content": content})
        if not cleaned_messages:
            raise ValueError("Для Ollama RP требуется хотя бы одно сообщение.")
        return {
            "model": self.model,
            "messages": cleaned_messages,
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": options.num_ctx,
                "num_predict": options.max_output_tokens,
                "temperature": options.temperature,
                "top_p": options.top_p,
                "min_p": options.min_p,
                "repeat_penalty": options.repeat_penalty,
            },
        }

    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        options: RoleplayGenerationOptions,
    ) -> str:
        body = self.request_body(messages, options)
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            payload = await asyncio.to_thread(self._read_json, request)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
            raise RoleplayProviderError(
                f"Ollama RP вернула HTTP {error.code}: {detail}"
            ) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RoleplayProviderError(f"Ollama RP недоступна: {error}") from error

        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        result = str(content or payload.get("response") or "").strip()
        if not result:
            reason = str(payload.get("done_reason") or "пустой ответ")
            raise RoleplayProviderError(f"Ollama RP не вернула текст: {reason}.")
        return result

    def _read_json(self, request: urllib.request.Request) -> dict[str, Any]:
        with urllib.request.urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:
            raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RoleplayProviderError("Ollama RP вернула не JSON-объект.")
        if payload.get("error"):
            raise RoleplayProviderError(str(payload["error"])[:1000])
        return payload


__all__ = (
    "OllamaRoleplayClient",
    "RoleplayGenerationOptions",
    "RoleplayProviderError",
)
