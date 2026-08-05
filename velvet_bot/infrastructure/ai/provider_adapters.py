from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from velvet_bot.domains.media_generation.provider_contract import (
    MediaProviderName,
    MediaProviderUsage,
    ProviderRoute,
)

if TYPE_CHECKING:
    from velvet_bot.domains.media_generation import (
        KieGenerationRequest,
        KieTaskRecord,
    )
    from . import KieClient


class KieProviderAdapter:
    provider = MediaProviderName.KIE

    def __init__(self, client: "KieClient") -> None:
        self._client = client

    def route(self, request: "KieGenerationRequest") -> ProviderRoute:
        return ProviderRoute(
            provider=self.provider,
            model_id=self._client.models.provider_model_for_request(request),
        )

    async def submit(
        self,
        request: "KieGenerationRequest",
        *,
        callback_url: str | None = None,
    ) -> str:
        return await self._client._submit_kie_task(
            request,
            callback_url=callback_url,
        )

    async def status(self, task_id: str) -> "KieTaskRecord":
        return await self._client._get_kie_task(task_id)

    async def cancel(self, task_id: str) -> bool:
        del task_id
        return False

    async def balance(self) -> Decimal:
        return await self._client._kie_balance()

    def usage(self, record: "KieTaskRecord") -> MediaProviderUsage:
        return MediaProviderUsage(
            provider=self.provider,
            provider_task_id=record.task_id,
            consumed_credits=record.consumed_credits,
            result_count=len(record.result_urls),
            terminal_state=record.state.value,
        )


class GrsProviderAdapter:
    provider = MediaProviderName.GRS

    def __init__(self, client: "KieClient") -> None:
        self._client = client

    def route(self, request: "KieGenerationRequest") -> ProviderRoute:
        return ProviderRoute(
            provider=self.provider,
            model_id=self._client.models.provider_model_for_request(request),
        )

    async def submit(
        self,
        request: "KieGenerationRequest",
        *,
        callback_url: str | None = None,
    ) -> str:
        del callback_url
        return await self._client._submit_grs_task(request)

    async def status(self, task_id: str) -> "KieTaskRecord":
        return await self._client._get_grs_task_record(task_id)

    async def cancel(self, task_id: str) -> bool:
        del task_id
        return False

    async def balance(self) -> Decimal:
        return await self._client._grs_balance()

    def usage(self, record: "KieTaskRecord") -> MediaProviderUsage:
        return MediaProviderUsage(
            provider=self.provider,
            provider_task_id=record.task_id,
            consumed_credits=record.consumed_credits,
            result_count=len(record.result_urls),
            terminal_state=record.state.value,
        )


__all__ = ("GrsProviderAdapter", "KieProviderAdapter")
