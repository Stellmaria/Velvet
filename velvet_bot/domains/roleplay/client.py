from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from velvet_bot.domains.roleplay.models import RoleplayMessage

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = frozenset({"openai", "openai_compatible"})


class RoleplayClientError(RuntimeError):
    """A configured text provider could not produce a usable response."""


@dataclass(frozen=True, slots=True)
class GeneratedRoleplayText:
    text: str
    provider: str
    model: str


class RoleplayClient(Protocol):
    async def generate(
        self,
        *,
        instructions: str,
        messages: Sequence[RoleplayMessage],
    ) -> GeneratedRoleplayText: ...


class TextRoleplayClient:
    """Small standard-library client for cloud Responses and chat APIs."""

    def __init__(self, *, provider: str, base_url: str, model: str, api_key: str | None,
                 timeout_seconds: int, max_output_tokens: int, max_attempts: int = 2) -> None:
        normalized_provider = provider.strip().casefold()
        if normalized_provider not in _SUPPORTED_PROVIDERS:
            raise ValueError(f"Неподдерживаемый text provider: {provider}.")
        normalized_url = base_url.strip().rstrip("/")
        normalized_model = model.strip()
        if not normalized_url:
            raise ValueError("Base URL text provider не может быть пустым.")
        if not normalized_model:
            raise ValueError("Название text-модели не может быть пустым.")
        if not api_key or not api_key.strip():
            raise ValueError("Облачный text provider требует API key.")
        self.provider = normalized_provider
        self.base_url = normalized_url
        self.model = normalized_model
        self.api_key = api_key.strip()
        self.timeout_seconds = max(10, int(timeout_seconds))
        self.max_output_tokens = max(128, int(max_output_tokens))
        self.max_attempts = max(1, int(max_attempts))

    async def generate(self, *, instructions: str,
                       messages: Sequence[RoleplayMessage]) -> GeneratedRoleplayText:
        last_error: RoleplayClientError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = await asyncio.to_thread(self._request_once, instructions, messages)
                text = self._extract_text(payload).strip()
                if not text:
                    raise RoleplayClientError(f"{self.provider}:{self.model} вернул пустой ответ.")
                return GeneratedRoleplayText(text=text, provider=self.provider, model=self.model)
            except RoleplayClientError as error:
                last_error = error
                if attempt >= self.max_attempts:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 4))
        if last_error is not None:
            raise last_error
        raise RoleplayClientError("Text provider завершился без ответа.")

    def _request_once(self, instructions: str,
                      messages: Sequence[RoleplayMessage]) -> dict[str, Any]:
        if self.provider == "openai":
            endpoint = f"{self.base_url}/responses"
            body = self._openai_responses_body(instructions, messages)
        else:
            endpoint = f"{self.base_url}/chat/completions"
            body = self._chat_completions_body(instructions, messages)
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[:1200]
            raise RoleplayClientError(
                f"{self.provider}:{self.model} HTTP {error.code}: {details}"
            ) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RoleplayClientError(
                f"{self.provider}:{self.model} недоступен: {error}"
            ) from error
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RoleplayClientError(
                f"{self.provider}:{self.model} вернул повреждённый JSON."
            ) from error
        if not isinstance(payload, dict):
            raise RoleplayClientError(
                f"{self.provider}:{self.model} вернул неожиданный ответ."
            )
        provider_error = payload.get("error")
        if provider_error:
            raise RoleplayClientError(f"{self.provider}:{self.model}: {provider_error}")
        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _openai_responses_body(self, instructions: str,
                               messages: Sequence[RoleplayMessage]) -> dict[str, Any]:
        return {
            "model": self.model,
            "instructions": instructions,
            "input": [{"role": message.role, "content": message.content}
                      for message in messages],
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }

    def _chat_completions_body(self, instructions: str,
                               messages: Sequence[RoleplayMessage]) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                *({"role": message.role, "content": message.content}
                  for message in messages),
            ],
            "max_tokens": self.max_output_tokens,
            "stream": False,
        }

    def _extract_text(self, payload: dict[str, Any]) -> str:
        if self.provider == "openai":
            return _extract_openai_response_text(payload)
        return _extract_chat_completion_text(payload)


class FailoverRoleplayClient:
    def __init__(self, primary: RoleplayClient, fallback: RoleplayClient) -> None:
        self._primary = primary
        self._fallback = fallback

    async def generate(self, *, instructions: str,
                       messages: Sequence[RoleplayMessage]) -> GeneratedRoleplayText:
        try:
            return await self._primary.generate(instructions=instructions, messages=messages)
        except RoleplayClientError as error:
            logger.warning("Primary roleplay provider failed, using fallback: %s", error)
            return await self._fallback.generate(instructions=instructions, messages=messages)


def _extract_openai_response_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    fragments: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                value = part.get("text") or part.get("refusal")
                if isinstance(value, str) and value.strip():
                    fragments.append(value.strip())
    if fragments:
        return "\n".join(fragments)
    raise RoleplayClientError(
        f"OpenAI Responses API не вернул текст: status={payload.get('status')!r}, "
        f"incomplete={payload.get('incomplete_details')!r}."
    )


def _extract_chat_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RoleplayClientError("OpenAI-compatible endpoint не вернул choices.")
    first = choices[0]
    if not isinstance(first, dict):
        raise RoleplayClientError("OpenAI-compatible choice имеет неверный формат.")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RoleplayClientError("OpenAI-compatible endpoint не вернул message.")
    content = message.get("content")
    if not isinstance(content, str):
        raise RoleplayClientError("OpenAI-compatible endpoint не вернул текст.")
    return content


__all__ = (
    "FailoverRoleplayClient",
    "GeneratedRoleplayText",
    "RoleplayClient",
    "RoleplayClientError",
    "TextRoleplayClient",
)
