from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID
from velvet_bot.application.media_delivery import MediaDeliveryJob, MediaDeliveryStatus, MediaDeliveryStepStatus
from velvet_bot.application.media_tasks import task_payload_mapping, task_result_urls
from velvet_bot.database import Database
from velvet_bot.infrastructure.media_delivery_repository_helpers import _TERMINAL_STATUSES, _VIDEO_MODELS, _error_text, _job_from_rows, _json, _text, delivery_metadata, first_text, media_kind, optional_int

class MediaDeliveryRepositoryBackfillMixin:

    async def backfill_missing_successes(self, *, limit: int=100) -> int:
        safe_limit = max(1, min(1000, int(limit)))
        async with self._database.acquire() as connection:
            rows = await connection.fetch("\n                SELECT task.id, task.payload, task.result\n                FROM ai_tasks AS task\n                LEFT JOIN media_delivery_jobs AS delivery ON delivery.task_id=task.id\n                WHERE task.status='success'\n                  AND task.task_type='media.generate.kie'\n                  AND delivery.task_id IS NULL\n                ORDER BY task.completed_at ASC NULLS LAST, task.created_at ASC\n                LIMIT $1::INTEGER\n                ", safe_limit)
        imported = 0
        for row in rows:
            if await self._backfill_row(row):
                imported += 1
        return imported

    async def backfill_task(self, *, task_id: UUID) -> bool:
        async with self._database.acquire() as connection:
            exists = await connection.fetchval('SELECT EXISTS(SELECT 1 FROM media_delivery_jobs WHERE task_id=$1::UUID)', task_id)
            if bool(exists):
                return True
            row = await connection.fetchrow("\n                SELECT id, payload, result\n                FROM ai_tasks\n                WHERE id=$1::UUID AND status='success' AND task_type='media.generate.kie'\n                ", task_id)
        return bool(row is not None and await self._backfill_row(row))

    async def _backfill_row(self, row: Mapping[str, object]) -> bool:
        task_id = UUID(str(row['id']))
        payload = task_payload_mapping(row.get('payload'))
        result = task_payload_mapping(row.get('result'))
        request = task_payload_mapping(payload.get('request'))
        runtime = task_payload_mapping(payload.get('kie_campaign'))
        provider_task_id = first_text(result.get('provider_task_id'), runtime.get('last_provider_task_id'), runtime.get('active_provider_task_id'))
        if provider_task_id is None:
            return False
        model = str(request.get('model') or '').strip()
        provider = str(result.get('provider') or ('grs' if model in {'nano_banana_2', 'nano_banana_pro'} else 'kie')).strip()
        chat_id = optional_int(payload.get('chat_id'))
        metadata = delivery_metadata(request)
        urls = task_result_urls(result)
        await self.record_provider_success(task_id=task_id, provider=provider, provider_task_id=provider_task_id, chat_id=chat_id, media_kind='video' if model in _VIDEO_MODELS else 'image', request=metadata, result_urls=urls)
        return True

__all__ = ("MediaDeliveryRepositoryBackfillMixin",)
