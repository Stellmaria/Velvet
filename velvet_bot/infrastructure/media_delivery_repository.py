from __future__ import annotations

from velvet_bot.infrastructure.media_delivery_repository_backfill import MediaDeliveryRepositoryBackfillMixin
from velvet_bot.infrastructure.media_delivery_repository_claim import MediaDeliveryRepositoryClaimMixin
from velvet_bot.infrastructure.media_delivery_repository_finish import MediaDeliveryRepositoryFinishMixin
from velvet_bot.infrastructure.media_delivery_repository_helpers import delivery_metadata, first_text, optional_int
from velvet_bot.infrastructure.media_delivery_repository_record import MediaDeliveryRepositoryRecordMixin

class PostgresMediaDeliveryRepository(
    MediaDeliveryRepositoryRecordMixin,
    MediaDeliveryRepositoryBackfillMixin,
    MediaDeliveryRepositoryClaimMixin,
    MediaDeliveryRepositoryFinishMixin,
):
    pass

__all__ = ("PostgresMediaDeliveryRepository", "delivery_metadata", "first_text", "optional_int")
