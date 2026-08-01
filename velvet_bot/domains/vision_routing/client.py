from __future__ import annotations

import asyncio
import base64
import json
import urllib.request
from typing import Mapping

from velvet_bot.ai_vision import (
    VisionAnalysisError,
    VisionClient,
    VisionProviderUnavailable,
    _extract_json_object,
)
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import (
    AIProviderResult,
    AIRequestContext,
    AIRequestExecutor,
)
from velvet_bot.domains.vision_routing.models import (
    VisionAnalysisMode,
    VisionProviderAnalysis,
    VisionRoute,
    VisionRouteConfig,
)
from velvet_bot.domains.vision_routing.profile_contract import (
    normalize_routed_profile,
    prompt_for_mode,
    schema_for_mode,
)

_MAX_OUTPUT_TOKENS = 1800


class MeteredVisionClient(VisionClient):
    """One explicitly routed VL model with budget reservation and usage capture."""

    ai_task_profile = "cascade"

    def __init__(
        self,
        *,
        config: VisionRouteConfig,
        executor: AIRequestExecutor[VisionProviderAnalysis],
    ) -> None:
        super().__init__(
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
        self.route = config.route
        self.mode = (
            VisionAnalysisMode.SENSITIVE
            if config.route is VisionRoute.SENSITIVE
            else VisionAnalysisMode.STANDARD
        )
        self.prompt_version = config.prompt_version
        self.schema_version = config.schema_version
        self.max_attempts = max(1, int(config.max_attempts))
        self._pricing = config.pricing
        self._executor = executor

    async def analyze_prepared(
        self,
        prepared: bytes,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        operation: str = "vision.semantic-profile",
        metadata: Mapping[str, object] | None = None,
    ) -> VisionProviderAnalysis:
        prompt = prompt_for_mode(self.mode)
        schema = schema_for_mode(self.mode)
        estimated_input_tokens = _estimate_input_tokens(
            prepared,
            prompt=prompt,
            schema=schema,
        )
        context_metadata = {
            "route": self.route.value,
            "analysis_mode": self.mode.value,
            "schema_version": self.schema_version,
            "prompt_version": self.prompt_version,
            "prepared_bytes": len(prepared),
            "max_output_tokens": _MAX_OUTPUT_TOKENS,
            "estimated_input_tokens": estimated_input_tokens,
            **dict(metadata or {}),
        }
        context = AIRequestContext(
            scope=AIBudgetScope.VISION,
            provider=self.provider,
            model=self.model,
            operation=operation,
            estimated_cost_rub=self._pricing.cost(
                input_tokens=estimated_input_tokens,
                output_tokens=_MAX_OUTPUT_TOKENS,
            ),
            user_id=user_id,
            chat_id=chat_id,
            metadata=context_metadata,
        )

        async def provider_operation() -> AIProviderResult[VisionProviderAnalysis]:
            analysis = await self._analyze_with_attempts(prepared)
            input_tokens = (
                analysis.input_tokens
                if analysis.usage_reported
                else estimated_input_tokens
            )
            output_tokens = (
                analysis.output_tokens
                if analysis.usage_reported
                else _estimate_profile_tokens(analysis.profile)
            )
            actual_cost = self._pricing.cost(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            metered = VisionProviderAnalysis(
                profile=analysis.profile,
                provider=analysis.provider,
                model=analysis.model,
                route=analysis.route,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usage_reported=analysis.usage_reported,
                actual_cost_rub=actual_cost,
            )
            return AIProviderResult(
                value=metered,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                actual_cost_rub=actual_cost,
                metadata={
                    "route": self.route.value,
                    "analysis_mode": self.mode.value,
                    "schema_version": self.schema_version,
                    "prompt_version": self.prompt_version,
                    "provider_reported_usage": analysis.usage_reported,
                    "attempt_limit": self.max_attempts,
                },
            )

        return await self._executor.execute(
            context=context,
            operation=provider_operation,
        )

    async def _analyze_with_attempts(self, prepared: bytes) -> VisionProviderAnalysis:
        last_error: VisionProviderUnavailable | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await asyncio.to_thread(self._request_once, prepared)
            except VisionProviderUnavailable as error:
                last_error = error
                if attempt >= self.max_attempts:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 4))
        if last_error is not None:
            raise last_error
        raise VisionProviderUnavailable("VL provider завершился без ответа.")

    def _request_once(self, prepared: bytes) -> VisionProviderAnalysis:
        image_base64 = base64.b64encode(prepared).decode("ascii")
        request = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(
                self._request_body(image_base64),
                ensure_ascii=False,
            ).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        payload = self._read_json(request, timeout=self.timeout_seconds)
        provider_error = payload.get("error")
        if provider_error:
            raise VisionAnalysisError(
                f"{self.provider}:{self.model}: {provider_error}"
            )
        content = _extract_provider_content(payload, provider=self.provider)
        profile = normalize_routed_profile(
            _extract_json_object(content),
            mode=self.mode,
            prompt_version=self.prompt_version,
        )
        input_tokens, output_tokens, usage_reported = _extract_usage(
            payload,
            provider=self.provider,
        )
        return VisionProviderAnalysis(
            profile=profile,
            provider=self.provider,
            model=self.model,
            route=self.route,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usage_reported=usage_reported,
        )

    def _endpoint(self) -> str:
        if self.provider == "ollama":
            return f"{self.base_url}/api/chat"
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        return f"{root}/v1/chat/completions"

    def _request_body(self, image_base64: str) -> dict[str, object]:
        prompt = prompt_for_mode(self.mode)
        schema = schema_for_mode(self.mode)
        if self.provider == "ollama":
            return {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_base64],
                    }
                ],
                "format": schema,
                "stream": False,
                "think": False,
                "options": {"temperature": 0},
            }
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            },
                        },
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": f"velvet_vision_{self.mode.value}",
                    "strict": True,
                    "schema": schema,
                },
            },
            "temperature": 0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
        }


def _extract_provider_content(
    payload: Mapping[str, object],
    *,
    provider: str,
) -> str:
    if provider == "ollama":
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content
        raise VisionAnalysisError("Ollama не вернула содержимое VL-ответа.")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise VisionAnalysisError("OpenAI-compatible VL endpoint не вернул choices.")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message, dict):
        raise VisionAnalysisError("OpenAI-compatible VL endpoint не вернул message.")
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        raise VisionAnalysisError(f"provider refusal: {refusal.strip()}")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        fragments = [
            str(item.get("text") or "").strip()
            for item in content
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
        if fragments:
            return "\n".join(fragments)
    raise VisionAnalysisError("OpenAI-compatible VL endpoint не вернул текст.")


def _extract_usage(
    payload: Mapping[str, object],
    *,
    provider: str,
) -> tuple[int, int, bool]:
    if provider == "ollama":
        input_tokens = _non_negative_int(payload.get("prompt_eval_count"))
        output_tokens = _non_negative_int(payload.get("eval_count"))
        reported = "prompt_eval_count" in payload or "eval_count" in payload
        return input_tokens, output_tokens, reported

    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0, 0, False
    input_tokens = _non_negative_int(
        usage.get("prompt_tokens", usage.get("input_tokens"))
    )
    output_tokens = _non_negative_int(
        usage.get("completion_tokens", usage.get("output_tokens"))
    )
    return input_tokens, output_tokens, True


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _estimate_input_tokens(
    prepared: bytes,
    *,
    prompt: str | None = None,
    schema: Mapping[str, object] | None = None,
) -> int:
    resolved_prompt = prompt or prompt_for_mode(VisionAnalysisMode.STANDARD)
    resolved_schema = schema or schema_for_mode(VisionAnalysisMode.STANDARD)
    schema_text = json.dumps(resolved_schema, ensure_ascii=False, separators=(",", ":"))
    prompt_tokens = max(1, (len(resolved_prompt) + len(schema_text) + 2) // 3)
    image_tokens = max(512, min(4096, (len(prepared) + 95) // 96))
    return prompt_tokens + image_tokens


def _estimate_profile_tokens(profile: Mapping[str, object]) -> int:
    serialized = json.dumps(dict(profile), ensure_ascii=False, default=str)
    return max(1, (len(serialized) + 2) // 3)


__all__ = (
    "MeteredVisionClient",
    "_estimate_input_tokens",
    "_extract_provider_content",
    "_extract_usage",
)
