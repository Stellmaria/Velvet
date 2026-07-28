from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage.models import AIProviderResult, AIRequestContext
from velvet_bot.domains.ai_usage.pricing import AITokenPricing
from velvet_bot.domains.ai_usage.service import AIRequestExecutor
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
    input_tokens: int = 0
    output_tokens: int = 0
    usage_reported: bool = False


class RoleplayClient(Protocol):
    async def generate(
        self,
        *,
        instructions: str,
        messages: Sequence[RoleplayMessage],
    ) -> GeneratedRoleplayText: ...


class TextRoleplayClient:
    """Small standard-library client for cloud Responses and chat APIs."""

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: int,
        max_output_tokens: int,
        max_attempts: int = 2,
        executor: AIRequestExecutor[GeneratedRoleplayText] | None = None,
        pricing: AITokenPricing | None = None,
    ) -> None:
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
        if (executor is None) != (pricing is None):
            raise ValueError("AI executor и token pricing должны быть заданы вместе.")
        self.provider = normalized_provider
        self.base_url = normalized_url
        self.model = normalized_model
        self.api_key = api_key.strip()
        self.timeout_seconds = max(10, int(timeout_seconds))
        self.max_output_tokens = max(128, int(max_output_tokens))
        self.max_attempts = max(1, int(max_attempts))
        self._executor = executor
        self._pricing = pricing

    async def generate(
        self,
        *,
        instructions: str,
        messages: Sequence[RoleplayMessage],
    ) -> GeneratedRoleplayText:
        if self._executor is None or self._pricing is None:
            return await self._generate_with_attempts(instructions, messages)

        estimated_input_tokens = _estimate_request_tokens(instructions, messages)
        context_message = messages[-1] if messages else None
        context = AIRequestContext(
            scope=AIBudgetScope.ROLEPLAY,
            provider=self.provider,
            model=self.model,
            operation="roleplay.generate",
            estimated_cost_rub=self._pricing.cost(
                input_tokens=estimated_input_tokens,
                output_tokens=self.max_output_tokens,
            ),
            user_id=context_message.user_id if context_message is not None else None,
            chat_id=context_message.chat_id if context_message is not None else None,
            metadata={
                "message_count": len(messages),
                "max_output_tokens": self.max_output_tokens,
                "estimated_input_tokens": estimated_input_tokens,
            },
        )

        async def operation() -> AIProviderResult[GeneratedRoleplayText]:
            generated = await self._generate_with_attempts(instructions, messages)
            input_tokens = (
                generated.input_tokens
                if generated.usage_reported
                else estimated_input_tokens
            )
            output_tokens = (
                generated.output_tokens
                if generated.usage_reported
                else _estimate_text_tokens(generated.text)
            )
            return AIProviderResult(
                value=generated,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                actual_cost_rub=self._pricing.cost(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                ),
                metadata={
                    "provider_reported_usage": generated.usage_reported,
                    "attempt_limit": self.max_attempts,
                },
            )

        return await self._executor.execute(context=context, operation=operation)

    async def _generate_with_attempts(
        self,
        instructions: str,
        messages: Sequence[RoleplayMessage],
    ) -> GeneratedRoleplayText:
        last_error: RoleplayClientError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = await asyncio.to_thread(
                    self._request_once,
                    instructions,
                    messages,
                )
                text = self._extract_text(payload).strip()
                if not text:
                    raise RoleplayClientError(
                        f"{self.provider}:{self.model} вернул пустой ответ."
                    )
                input_tokens, output_tokens, usage_reported = _extract_token_usage(
                    payload,
                    provider=self.provider,
                )
                return GeneratedRoleplayText(
                    text=text,
                    provider=self.provider,
                    model=self.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    usage_reported=usage_reported,
                )
            except RoleplayClientError as error:
                last_error = error
                if attempt >= self.max_attempts:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 4))
        if last_error is not None:
            raise last_error
        raise RoleplayClientError("Text provider завершился без ответа.")

    def _request_once(
        self,
        instructions: str,
        messages: Sequence[RoleplayMessage],
    ) -> dict[str, Any]:
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

    def _openai_responses_body(
        self,
        instructions: str,
        messages: Sequence[RoleplayMessage],
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "instructions": instructions,
            "input": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }

    def _chat_completions_body(
        self,
        instructions: str,
        messages: Sequence[RoleplayMessage],
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                *(
                    {"role": message.role, "content": message.content}
                    for message in messages
                ),
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

    async def generate(
        self,
        *,
        instructions: str,
        messages: Sequence[RoleplayMessage],
    ) -> GeneratedRoleplayText:
        try:
            return await self._primary.generate(
                instructions=instructions,
                messages=messages,
            )
        except RoleplayClientError as error:
            logger.warning("Primary roleplay provider failed, using fallback: %s", error)
            return await self._fallback.generate(
                instructions=instructions,
                messages=messages,
            )


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


def _extract_token_usage(
    payload: dict[str, Any],
    *,
    provider: str,
) -> tuple[int, int, bool]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0, 0, False
    if provider == "openai":
        input_value = usage.get("input_tokens")
        output_value = usage.get("output_tokens")
    else:
        input_value = usage.get("prompt_tokens")
        output_value = usage.get("completion_tokens")
    if not _is_token_count(input_value) or not _is_token_count(output_value):
        return 0, 0, False
    return int(input_value), int(output_value), True


def _is_token_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _estimate_request_tokens(
    instructions: str,
    messages: Sequence[RoleplayMessage],
) -> int:
    content = [instructions]
    content.extend(message.content for message in messages)
    role_overhead = len(messages) * 8
    return max(1, sum(_estimate_text_tokens(item) for item in content) + role_overhead)


def _estimate_text_tokens(text: str) -> int:
    return max(1, (len(text) + 1) // 2)


__all__ = (
    "FailoverRoleplayClient",
    "GeneratedRoleplayText",
    "RoleplayClient",
    "RoleplayClientError",
    "TextRoleplayClient",
)
