from __future__ import annotations

import asyncio
import os
import urllib.parse
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from velvet_bot.domains.media_generation import KieGenerationRequest
from velvet_bot.domains.media_generation.provider_contract import (
    MediaProviderName,
    MediaProviderRegistry,
    MediaProviderUsage,
    ProviderRoute,
    extract_provider_credits,
    with_image_output_guard,
)

from .kie import (
    KieClient as BaseKieClient,
    KieError,
    KieProtocolError,
    KieTaskFailed,
    KieTransientError,
    _build_wan_27_input,
)
from .provider_adapters import GrsProviderAdapter, KieProviderAdapter

_GROK_V1_IMAGE_TO_VIDEO = "grok-imagine/image-to-video"
_WAN_27_IMAGE_TO_VIDEO = "wan/2-7-image-to-video"
_GRS_TASK_PREFIX = "grs:"


class KieClient(BaseKieClient):
    """Compatibility façade backed by explicit provider adapters."""

    def __init__(
        self,
        *,
        grs_api_key: str | None = None,
        grs_base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        mocked_transport = kwargs.get("transport") is not None
        resolved_grs_key = grs_api_key
        resolved_grs_base_url = grs_base_url
        if not mocked_transport:
            if resolved_grs_key is None:
                resolved_grs_key = os.getenv("GRS_API_KEY", "")
            if resolved_grs_base_url is None:
                resolved_grs_base_url = os.getenv(
                    "GRS_BASE_URL",
                    "https://grsaiapi.com",
                )
        super().__init__(
            grs_api_key=(resolved_grs_key if resolved_grs_key is not None else " "),
            grs_base_url=resolved_grs_base_url or "https://grsaiapi.com",
            **kwargs,
        )
        self._provider_registry = MediaProviderRegistry(
            {
                MediaProviderName.KIE: KieProviderAdapter(self),
                MediaProviderName.GRS: GrsProviderAdapter(self),
            }
        )

    @property
    def provider_registry(self) -> MediaProviderRegistry:
        return self._provider_registry

    def provider_route(self, request: KieGenerationRequest) -> ProviderRoute:
        return self._provider_registry.route(request)

    def provider_usage(self, record) -> MediaProviderUsage:
        return self._provider_registry.for_task_id(record.task_id).usage(record)

    async def create_task(
        self,
        request: KieGenerationRequest,
        *,
        callback_url: str | None = None,
    ) -> str:
        return await self._provider_registry.for_request(request).submit(
            request,
            callback_url=callback_url,
        )

    async def get_task(self, task_id: str):
        task_id_text = str(task_id).strip()
        if not task_id_text:
            raise ValueError("task_id не может быть пустым.")
        return await self._provider_registry.for_task_id(task_id_text).status(task_id_text)

    async def cancel_task(self, task_id: str) -> bool:
        task_id_text = str(task_id).strip()
        if not task_id_text:
            raise ValueError("task_id не может быть пустым.")
        return await self._provider_registry.for_task_id(task_id_text).cancel(task_id_text)

    async def _submit_kie_task(
        self,
        request: KieGenerationRequest,
        *,
        callback_url: str | None = None,
    ) -> str:
        provider_model = self.models.provider_model_for_request(request)
        provider_input: Mapping[str, object] = request.to_input()
        if provider_model == _GROK_V1_IMAGE_TO_VIDEO:
            grok_input = dict(provider_input)
            grok_input.pop("aspect_ratio", None)
            grok_input.pop("duration", None)
            grok_input.pop("mode", None)
            provider_input = grok_input
        elif provider_model == _WAN_27_IMAGE_TO_VIDEO:
            provider_input = _build_wan_27_input(provider_input)
        payload: dict[str, object] = {
            "model": provider_model,
            "input": dict(provider_input),
        }
        if callback_url and callback_url.strip():
            payload["callBackUrl"] = callback_url.strip()
        response = await asyncio.to_thread(
            self._transport,
            "POST",
            f"{self.base_url}/jobs/createTask",
            self._headers(self.api_key),
            payload,
            self.timeout_seconds,
        )
        self._ensure_kie_success(response, operation="createTask")
        data = response.get("data")
        task_id = data.get("taskId") if isinstance(data, Mapping) else None
        task_id_text = str(task_id or "").strip()
        if not task_id_text:
            raise KieProtocolError("Kie.ai createTask не вернул taskId.")
        return task_id_text

    async def _submit_grs_task(self, request: KieGenerationRequest) -> str:
        if self.grs_api_key is None:
            raise KieError("Для Nano Banana 2/Pro не задан GRS_API_KEY.")
        guarded = with_image_output_guard(request)
        model_id = self.models.provider_model_for_request(guarded)
        payload = guarded.to_grs_input(model_id=model_id)
        payload["replyType"] = "async"
        response = await asyncio.to_thread(
            self._transport,
            "POST",
            f"{self.grs_base_url}/v1/api/generate",
            self._headers(self.grs_api_key),
            payload,
            self.timeout_seconds,
        )
        raw_task_id = str(response.get("id") or "").strip()
        if not raw_task_id:
            message = str(
                response.get("message")
                or response.get("msg")
                or response.get("error")
                or "GRS AI не вернул id асинхронной задачи."
            )
            raise KieProtocolError(message)
        task_id = f"{_GRS_TASK_PREFIX}{raw_task_id}"
        self._grs_initial_responses[task_id] = dict(response)
        return task_id

    async def _get_kie_task(self, task_id: str):
        return await super().get_task(task_id)

    async def _get_grs_task_record(self, task_id: str):
        return await super()._get_grs_task(task_id)

    async def _grs_balance(self) -> Decimal:
        api_key = self.grs_api_key
        if api_key is None:
            raise KieError("Для проверки баланса не задан GRS_API_KEY.")
        query = urllib.parse.urlencode({"apikey": api_key})
        attempts: tuple[tuple[str, str, Mapping[str, object] | None], ...] = (
            (
                "GET",
                f"{self.grs_base_url}/client/common/getCredits?{query}",
                None,
            ),
            (
                "POST",
                f"{self.grs_base_url}/client/openapi/getAPIKeyCredits",
                {"apikey": api_key},
            ),
            (
                "POST",
                f"{self.grs_base_url}/client/openapi/getAPIKeyCredits",
                {"apiKey": api_key},
            ),
        )
        for method, url, payload in attempts:
            try:
                response = await asyncio.to_thread(
                    self._transport,
                    method,
                    url,
                    self._headers(api_key),
                    payload,
                    self.timeout_seconds,
                )
            except KieError:
                continue
            credits = extract_provider_credits(response)
            if credits is not None:
                return credits
        raise KieTransientError("Не удалось получить текущий баланс GRS AI.")

    async def _kie_balance(self) -> Decimal:
        response = await asyncio.to_thread(
            self._transport,
            "GET",
            f"{self.base_url}/chat/credit",
            self._headers(self.api_key),
            None,
            self.timeout_seconds,
        )
        self._ensure_kie_success(response, operation="chat/credit")
        credits = extract_provider_credits(response.get("data"))
        if credits is None:
            raise KieProtocolError("Kie.ai chat/credit не вернул числовой баланс.")
        return credits

    async def get_grs_credits(self) -> Decimal:
        return await self._provider_registry.for_task_id("grs:balance").balance()

    async def get_account_credits(self) -> Decimal:
        return await self._provider_registry.for_task_id("kie-balance").balance()


__all__ = (
    "GrsProviderAdapter",
    "KieClient",
    "KieError",
    "KieProtocolError",
    "KieProviderAdapter",
    "KieTaskFailed",
    "KieTransientError",
)
