from __future__ import annotations

import asyncio
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from velvet_bot.domains.media_generation import KieGenerationRequest

from .kie import (
    KieClient as BaseKieClient,
    KieError,
    KieProtocolError,
    KieTaskFailed,
    KieTransientError,
)

_GROK_V1_IMAGE_TO_VIDEO = "grok-imagine/image-to-video"


class KieClient(BaseKieClient):
    """Hybrid GRS/Kie client with exact legacy Grok v1 compatibility."""

    async def create_task(
        self,
        request: KieGenerationRequest,
        *,
        callback_url: str | None = None,
    ) -> str:
        if request.model.is_grs:
            return await super().create_task(request, callback_url=callback_url)
        provider_model = self.models.provider_model_for_request(request)
        provider_input = dict(request.to_input())
        if provider_model == _GROK_V1_IMAGE_TO_VIDEO:
            # Single-image Grok v1 derives framing and motion defaults from the
            # source image. Keep the owner-facing flow minimal and send only the
            # documented controls that matter here. nsfw_checker=false is kept
            # intentionally so Kie does not apply its additional content filter.
            provider_input.pop("aspect_ratio", None)
            provider_input.pop("duration", None)
            provider_input.pop("mode", None)
        payload: dict[str, object] = {
            "model": provider_model,
            "input": provider_input,
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
            raise KieProtocolError("Kie.ai chat/credit вернул некорректный баланс.")
        return credits


__all__ = (
    "KieClient",
    "KieError",
    "KieProtocolError",
    "KieTaskFailed",
    "KieTransientError",
)
