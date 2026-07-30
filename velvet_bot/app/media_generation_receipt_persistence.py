from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from asyncpg import PostgresError

from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import KieGenerationRequest, KieTaskRecord

from .media_generation_receipt_core import CostInfo, DeliveryStats, ReceiptContext

logger = logging.getLogger(__name__)


async def persist_receipt_stats(
    worker: FriendlyKieGenerationWorker,
    *,
    context: ReceiptContext | None,
    request: KieGenerationRequest,
    record: KieTaskRecord,
    cost: CostInfo,
    provider_latency_ms: int | None,
    total_elapsed_ms: int | None,
    delivery: DeliveryStats,
) -> None:
    if context is None:
        return
    queue = getattr(worker, "_campaign_queue", None) or getattr(worker, "_queue", None)
    database = getattr(queue, "_database", None)
    if database is None:
        return
    stats = {
        "provider": "grs" if request.model.is_grs else "kie",
        "provider_model": worker._client.models.provider_model_for_request(request),
        "model_alias": request.model.value,
        "media_type": "video" if request.model.is_video else "photo",
        "resolution": request.resolution,
        "duration_seconds": request.duration_seconds if request.model.is_video else None,
        "reference_count": len(request.references),
        "content_mode": request.content_mode.value,
        "provider_task_id": record.task_id,
        "provider_attempt_count": context.provider_attempt or 1,
        "queue_attempt_count": context.task.attempt_count,
        "credits_consumed": str(cost.credits) if cost.credits is not None else None,
        "actual_cost_usd": str(cost.usd),
        "actual_cost_rub": str(cost.rub),
        "cost_source": cost.source,
        "cost_approximate": cost.approximate,
        "provider_latency_ms": provider_latency_ms,
        "total_elapsed_ms": total_elapsed_ms,
        "delivery_elapsed_ms": delivery.delivery_elapsed_ms,
        "result_count": delivery.result_count,
        "result_bytes": delivery.result_bytes,
        "preview_delivery_status": delivery.preview_status,
        "original_delivery_status": delivery.original_status,
        "delivery_errors": list(delivery.errors),
        "delivered_at": datetime.now(timezone.utc).isoformat(),
    }
    encoded = json.dumps({"media_receipt": stats}, ensure_ascii=False, default=str)
    metadata = json.dumps(stats, ensure_ascii=False, default=str)
    try:
        async with database.acquire() as connection:
            await connection.execute(
                """UPDATE ai_tasks SET result=result || $2::JSONB,updated_at=NOW()
                   WHERE id=$1::UUID""",
                context.task.id,
                encoded,
            )
            await connection.execute(
                """UPDATE ai_usage_events
                   SET actual_cost_rub=$2::NUMERIC,
                       latency_ms=COALESCE($3::BIGINT,latency_ms),
                       metadata=metadata || $4::JSONB
                   WHERE id=(SELECT id FROM ai_usage_events
                       WHERE metadata->>'queue_task_id'=$1 AND status='success'
                       ORDER BY completed_at DESC NULLS LAST,id DESC LIMIT 1)""",
                str(context.task.id),
                cost.rub,
                provider_latency_ms,
                metadata,
            )
    except (PostgresError, RuntimeError, ValueError):
        logger.exception("Could not persist media receipt stats task=%s", context.task.id)
