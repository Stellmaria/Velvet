from __future__ import annotations

import os
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from velvet_bot.core.config import Settings
from velvet_bot.domains.vision_batches.models import (
    VisionBatchError,
    VisionBatchPlan,
    VisionBatchStatus,
)
from velvet_bot.domains.vision_batches.service import (
    VisionBatchService,
    _vision_cascade_max_cost,
)
from velvet_bot.domains.vision_batches.worker import VisionBatchQueueConsumer


def _settings(*, provider: str = "ollama") -> Settings:
    return Settings(
        bot_token="token",
        database_url="postgresql://test",
        allowed_user_ids=frozenset({1}),
        allowed_usernames=frozenset(),
        log_chat_id=None,
        analytics_channel_ids=frozenset(),
        publication_timezone="Europe/Berlin",
        backup_dir="backups",
        pg_dump_path="pg_dump",
        pg_restore_path="pg_restore",
        ai_vision_enabled=True,
        ai_vision_provider=provider,
        ai_vision_base_url="http://vision/v1",
        ai_vision_model="flash-model",
        ai_vision_api_key="key" if provider != "ollama" else None,
    )


def _plan(*, candidate_ids: tuple[int, ...] = (10, 20)) -> VisionBatchPlan:
    return VisionBatchPlan(
        id=uuid4(),
        task_type="vision.semantic-profile",
        status=VisionBatchStatus.PLANNED,
        candidate_ids=candidate_ids,
        candidate_count=len(candidate_ids),
        created_task_count=0,
        deduplicated_task_count=0,
        max_cost_per_item_rub=Decimal("1.25"),
        estimated_cost_rub=Decimal("2.50"),
        prompt_version=3,
        created_by=1,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        started_at=None,
        completed_at=None,
        last_error=None,
    )


class _FakeUsage:
    def __init__(
        self,
        *,
        daily: str = "100",
        monthly: str = "100",
        max_request: str = "250",
    ) -> None:
        self.daily = Decimal(daily)
        self.monthly = Decimal(monthly)
        self.max_request = Decimal(max_request)
        self.paused = False

    async def status(self):
        return SimpleNamespace(
            daily_remaining_rub=self.daily,
            ordinary_month_remaining_rub=self.monthly,
            max_request_rub=self.max_request,
            paused=self.paused,
            pause_reason=None,
        )


class _FakeRepository:
    def __init__(self, plan: VisionBatchPlan | None = None) -> None:
        self.plan_value = plan
        self.created_kwargs = None
        self.attached = ()
        self.marked_counts = None
        self.error = None

    async def find_candidates(self, *, limit: int):
        return (10, 20)[:limit]

    async def create_plan(self, **kwargs):
        self.created_kwargs = kwargs
        plan = _plan(candidate_ids=tuple(kwargs["candidate_ids"]))
        self.plan_value = replace(
            plan,
            id=kwargs["plan_id"],
            max_cost_per_item_rub=kwargs["max_cost_per_item_rub"],
            estimated_cost_rub=kwargs["estimated_cost_rub"],
            prompt_version=kwargs["prompt_version"],
            expires_at=kwargs["expires_at"],
            metadata=kwargs["metadata"],
        )
        return self.plan_value

    async def get(self, *, plan_id):
        return self.plan_value if self.plan_value and self.plan_value.id == plan_id else None

    async def latest(self, *, created_by=None):
        return self.plan_value

    async def claim_start(self, *, plan_id):
        if self.plan_value is None or self.plan_value.id != plan_id:
            return None
        if self.plan_value.expires_at <= datetime.now(timezone.utc):
            self.plan_value = replace(
                self.plan_value,
                status=VisionBatchStatus.EXPIRED,
            )
            return None
        self.plan_value = replace(
            self.plan_value,
            status=VisionBatchStatus.STARTING,
        )
        return self.plan_value

    async def attach_created_tasks(self, *, plan_id, task_ids):
        self.attached = tuple(task_ids)
        return len(self.attached)

    async def mark_queued(
        self,
        *,
        plan_id,
        created_task_count,
        deduplicated_task_count,
    ):
        self.marked_counts = (created_task_count, deduplicated_task_count)
        self.plan_value = replace(
            self.plan_value,
            status=VisionBatchStatus.QUEUED,
            created_task_count=created_task_count,
            deduplicated_task_count=deduplicated_task_count,
        )
        return self.plan_value

    async def mark_error(self, *, plan_id, error):
        self.error = error

    async def progress(self, *, plan_id):
        return SimpleNamespace(plan=self.plan_value)

    async def cancel(self, *, plan_id, reason):
        return self.plan_value


class _FakeQueue:
    def __init__(self) -> None:
        self.requests = ()
        self.completed = None
        self.failed = None
        self.task = None

    async def enqueue_many(self, requests):
        self.requests = tuple(requests)
        return (
            SimpleNamespace(task=SimpleNamespace(id=uuid4()), created=True),
            SimpleNamespace(task=SimpleNamespace(id=uuid4()), created=False),
        )[: len(self.requests)]

    async def claim_next(self, **kwargs):
        task, self.task = self.task, None
        return task

    async def complete(self, **kwargs):
        self.completed = kwargs
        return SimpleNamespace(id=kwargs["task_id"])

    async def fail(self, **kwargs):
        self.failed = kwargs
        return None

    async def heartbeat(self, **kwargs):
        return True


class _FakeProcessor:
    async def process_media_id(self, media_id: int) -> dict[str, object]:
        return {"media_id": media_id, "route": "flash"}


class VisionBatchServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_calculates_conservative_cost_without_provider_call(self) -> None:
        repository = _FakeRepository()
        service = VisionBatchService(
            repository=repository,
            queue_service=_FakeQueue(),
            usage_service=_FakeUsage(),
            settings=_settings(provider="openai_compatible"),
        )
        env = {
            "AI_VISION_FLASH_INPUT_RUB_PER_1M": "100",
            "AI_VISION_FLASH_OUTPUT_RUB_PER_1M": "100",
            "AI_VISION_PRO_MODEL": "",
            "AI_VISION_SENSITIVE_MODEL": "",
            "AI_VISION_QUEUE_ENABLED": "true",
        }
        with patch.dict(os.environ, env, clear=False):
            plan = await service.plan(limit=2, created_by=1)
        self.assertEqual(Decimal("0.7200"), plan.max_cost_per_item_rub)
        self.assertEqual(Decimal("1.4400"), plan.estimated_cost_rub)
        self.assertEqual((10, 20), plan.candidate_ids)
        self.assertTrue(plan.metadata["within_per_request_limit"])
        self.assertTrue(plan.metadata["within_current_budget"])

    async def test_start_rechecks_budget_and_records_deduplication(self) -> None:
        plan = _plan()
        repository = _FakeRepository(plan)
        queue = _FakeQueue()
        service = VisionBatchService(
            repository=repository,
            queue_service=queue,
            usage_service=_FakeUsage(),
            settings=_settings(),
        )
        with patch.dict(os.environ, {"AI_VISION_QUEUE_ENABLED": "true"}, clear=False):
            started = await service.start(plan_id=plan.id, created_by=1)
        self.assertEqual(VisionBatchStatus.QUEUED, started.status)
        self.assertEqual((1, 1), repository.marked_counts)
        self.assertEqual(2, len(queue.requests))
        self.assertEqual("vision.semantic-profile", queue.requests[0].task_type)
        self.assertEqual(10, queue.requests[0].payload["media_id"])
        self.assertEqual(1, len(repository.attached))

    async def test_start_is_blocked_when_queue_feature_is_disabled(self) -> None:
        plan = _plan()
        service = VisionBatchService(
            repository=_FakeRepository(plan),
            queue_service=_FakeQueue(),
            usage_service=_FakeUsage(),
            settings=_settings(),
        )
        with patch.dict(os.environ, {"AI_VISION_QUEUE_ENABLED": "false"}, clear=False):
            with self.assertRaisesRegex(VisionBatchError, "AI_VISION_QUEUE_ENABLED"):
                await service.start(plan_id=plan.id, created_by=1)

    async def test_start_is_blocked_when_batch_exceeds_remaining_budget(self) -> None:
        plan = _plan()
        service = VisionBatchService(
            repository=_FakeRepository(plan),
            queue_service=_FakeQueue(),
            usage_service=_FakeUsage(daily="1", monthly="100"),
            settings=_settings(),
        )
        with patch.dict(os.environ, {"AI_VISION_QUEUE_ENABLED": "true"}, clear=False):
            with self.assertRaisesRegex(VisionBatchError, "дневной"):
                await service.start(plan_id=plan.id, created_by=1)

    async def test_start_is_blocked_by_per_request_limit(self) -> None:
        plan = _plan()
        service = VisionBatchService(
            repository=_FakeRepository(plan),
            queue_service=_FakeQueue(),
            usage_service=_FakeUsage(max_request="1"),
            settings=_settings(),
        )
        with patch.dict(os.environ, {"AI_VISION_QUEUE_ENABLED": "true"}, clear=False):
            with self.assertRaisesRegex(VisionBatchError, "per-request"):
                await service.start(plan_id=plan.id, created_by=1)

    def test_cloud_cascade_cost_sums_only_configured_routes(self) -> None:
        env = {
            "AI_VISION_FLASH_INPUT_RUB_PER_1M": "100",
            "AI_VISION_FLASH_OUTPUT_RUB_PER_1M": "100",
            "AI_VISION_PRO_MODEL": "",
            "AI_VISION_SENSITIVE_MODEL": "",
        }
        with patch.dict(os.environ, env, clear=False):
            cost = _vision_cascade_max_cost(_settings(provider="openai_compatible"))
        self.assertEqual(Decimal("0.7200"), cost)


class VisionBatchConsumerTests(unittest.IsolatedAsyncioTestCase):
    async def test_consumer_completes_claimed_media_task(self) -> None:
        queue = _FakeQueue()
        task_id = uuid4()
        queue.task = SimpleNamespace(id=task_id, payload={"media_id": 77})
        consumer = VisionBatchQueueConsumer(
            queue_service=queue,
            processor=_FakeProcessor(),  # type: ignore[arg-type]
            heartbeat_seconds=3600,
        )
        processed = await consumer.process_once()
        self.assertEqual(1, processed)
        self.assertEqual(task_id, queue.completed["task_id"])
        self.assertEqual(77, queue.completed["result"]["media_id"])
        self.assertIsNone(queue.failed)


if __name__ == "__main__":
    unittest.main()
