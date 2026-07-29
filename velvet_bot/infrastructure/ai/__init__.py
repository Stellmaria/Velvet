from __future__ import annotations

import asyncio
import os
import urllib.parse
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from velvet_bot.domains.media_generation import KieGenerationRequest

from .kie import (
    KieClient as BaseKieClient,
    KieError,
    KieProtocolError,
    KieTaskFailed,
    KieTransientError,
    _build_wan_27_input,
)

_GROK_V1_IMAGE_TO_VIDEO = "grok-imagine/image-to-video"
_WAN_27_IMAGE_TO_VIDEO = "wan/2-7-image-to-video"
_GRS_TASK_PREFIX = "grs:"


class KieClient(BaseKieClient):
    """Hybrid GRS/Kie client with exact provider compatibility."""

    def __init__(
        self,
        *,
        grs_api_key: str | None = None,
        grs_base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Runtime clients may use the configured environment for backward
        # compatibility. Mocked clients must never inherit production secrets,
        # otherwise local unit tests become accidental live provider calls.
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
            grs_api_key=(
                resolved_grs_key
                if resolved_grs_key is not None
                else " "
            ),
            grs_base_url=resolved_grs_base_url or "https://grsaiapi.com",
            **kwargs,
        )

    async def create_task(
        self,
        request: KieGenerationRequest,
        *,
        callback_url: str | None = None,
    ) -> str:
        if request.model.is_grs:
            return await super().create_task(request, callback_url=callback_url)
        provider_model = self.models.provider_model_for_request(request)
        provider_input: Mapping[str, object] = request.to_input()
        if provider_model == _GROK_V1_IMAGE_TO_VIDEO:
            # Single-image Grok v1 derives framing and motion defaults from the
            # source image. Keep the owner-facing flow minimal and send only the
            # documented controls that matter here. nsfw_checker=false is kept
            # intentionally so Kie does not apply its additional content filter.
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

    async def _create_grs_task(self, request: KieGenerationRequest) -> str:
        """Submit GRS work asynchronously so image generation cannot time out the POST."""

        if self.grs_api_key is None:
            raise KieError("Для Nano Banana 2/Pro не задан GRS_API_KEY.")
        model_id = self.models.provider_model_for_request(request)
        payload = request.to_grs_input(model_id=model_id)
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

    async def get_grs_credits(self) -> Decimal:
        """Return the current GRS API-key balance without exposing the key in errors."""

        if self.grs_api_key is None:
            raise KieError("Для проверки баланса не задан GRS_API_KEY.")
        query = urllib.parse.urlencode({"apikey": self.grs_api_key})
        try:
            response = await asyncio.to_thread(
                self._transport,
                "GET",
                f"{self.grs_base_url}/client/common/getCredits?{query}",
                self._headers(self.grs_api_key),
                None,
                self.timeout_seconds,
            )
        except KieError:
            raise KieTransientError("Не удалось получить баланс GRS AI.") from None

        code = response.get("code")
        if code not in (None, 200, "200"):
            raise KieError("GRS AI отклонил запрос баланса.")
        raw_value: object = response.get("data")
        if isinstance(raw_value, Mapping):
            raw_value = (
                raw_value.get("credits")
                or raw_value.get("balance")
                or raw_value.get("value")
            )
        if raw_value is None:
            raw_value = response.get("credits") or response.get("balance")
        try:
            credits = Decimal(str(raw_value).strip())
        except (InvalidOperation, ValueError) as error:
            raise KieProtocolError("GRS AI не вернул числовой баланс кредитов.") from error
        if not credits.is_finite() or credits < 0:
            raise KieProtocolError("GRS AI вернул некорректный баланс кредитов.")
        return credits

    async def get_account_credits(self) -> Decimal:
        """Return the live Kie account balance from the official Common API."""

        response = await asyncio.to_thread(
            self._transport,
            "GET",
            f"{self.base_url}/chat/credit",
            self._headers(self.api_key),
            None,
            self.timeout_seconds,
        )
        self._ensure_kie_success(response, operation="chat/credit")
        raw_value = response.get("data")
        try:
            credits = Decimal(str(raw_value).strip())
        except (InvalidOperation, ValueError) as error:
            raise KieProtocolError("Kie.ai chat/credit не вернул числовой баланс.") from error
        if not credits.is_finite() or credits < 0:
            raise KieProtocolError("Kie.ai вернул некорректный баланс кредитов.")
        return credits


__all__ = (
    "KieClient",
    "KieError",
    "KieProtocolError",
    "KieTaskFailed",
    "KieTransientError",
)
