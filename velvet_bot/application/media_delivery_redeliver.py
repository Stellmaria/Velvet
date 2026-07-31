from __future__ import annotations

from uuid import UUID
from velvet_bot.application.media_delivery_deliver import DeliverMediaResult
from velvet_bot.application.media_delivery_models import MediaDeliveryRepository, MediaDeliverySummary

class RedeliverMediaResult:
    """Explicitly resend an existing provider result without calling generation APIs."""

    def __init__(self, *, repository: MediaDeliveryRepository, delivery: DeliverMediaResult) -> None:
        self._repository = repository
        self._delivery = delivery

    async def execute(self, *, task_id: UUID, chat_id: int) -> MediaDeliverySummary | None:
        await self._repository.backfill_task(task_id=task_id)
        reset = await self._repository.reset_for_redelivery(task_id=task_id, chat_id=chat_id)
        if not reset:
            return None
        return await self._delivery.execute(task_id=task_id)

__all__ = ("RedeliverMediaResult",)
