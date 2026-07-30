from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from velvet_bot.domains.ai_usage import AIRequestExecutor, AIUsageService
from velvet_bot.domains.media_generation.models import KieGenerationRequest, KiePricing
from velvet_bot.infrastructure.ai import KieClient

from .models import AufProvider
from .queue import ProviderAufTaskQueueService
from .store import AufRuntimeRepository

logger = logging.getLogger(__name__)

_KIE_SUBMISSION_LIMIT = 20
_KIE_SUBMISSION_WINDOW_SECONDS = 10.0
_DISPATCH_INTERVAL_SECONDS = 0.25
_SETTINGS_CACHE_SECONDS = 2.0


class _SubmissionRateLimiter:
    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self._limit = max(1, int(limit))
        self._window_seconds = max(0.1, float(window_seconds))
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= self._window_seconds:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._limit:
                    self._timestamps.append(now)
                    return
                delay = self._window_seconds - (now - self._timestamps[0])
            await asyncio.sleep(max(0.01, delay))


class ProviderAwareKieClient:
    """Delegate to KieClient while respecting Kie createTask rate limits."""

    def __init__(self, client: KieClient) -> None:
        self._client = client
        self._kie_submissions = _SubmissionRateLimiter(
            limit=_KIE_SUBMISSION_LIMIT,
            window_seconds=_KIE_SUBMISSION_WINDOW_SECONDS,
        )

    @property
    def models(self):
        return self._client.models

    async def create_task(
        self,
        request: KieGenerationRequest,
        *,
        callback_url: str | None = None,
    ) -> str:
        if not request.model.is_grs:
            await self._kie_submissions.acquire()
        return await self._client.create_task(request, callback_url=callback_url)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class AufGenerationDispatcher:
    """Run only the number of media jobs permitted by live database settings."""

    def __init__(
        self,
        *,
        bot,
        database,
        client: KieClient,
        usage_service: AIUsageService,
        pricing: KiePricing,
        usd_to_rub,
        max_attempts: int,
        worker_class: Callable[..., Any],
    ) -> None:
        self._bot = bot
        self._runtime = AufRuntimeRepository(database)
        self._client = ProviderAwareKieClient(client)
        self._usage_service = usage_service
        self._pricing = pricing
        self._usd_to_rub = usd_to_rub
        self._max_attempts = max_attempts
        self._worker_class = worker_class
        self._queues = {
            provider: ProviderAufTaskQueueService(
                database=database,
                provider=provider,
                max_attempts=max_attempts,
            )
            for provider in AufProvider
        }
        self._active: dict[AufProvider, set[asyncio.Task[int]]] = {
            provider: set() for provider in AufProvider
        }
        self._sequence = 0
        self._settings = None
        self._settings_loaded_at = 0.0

    async def run(self) -> None:
        try:
            while True:
                await self._dispatch_iteration()
                await asyncio.sleep(_DISPATCH_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            tasks = tuple(
                task
                for provider_tasks in self._active.values()
                for task in provider_tasks
            )
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _dispatch_iteration(self) -> None:
        self._drop_finished()
        settings = await self._runtime_settings()
        for provider in (AufProvider.GRS, AufProvider.KIE):
            queue = self._queues[provider]
            configured_limit = settings.limit_for(provider)
            database_running = await queue.running_count()
            live_tasks = len(self._active[provider])
            occupied = max(database_running, live_tasks)
            available = max(0, configured_limit - occupied)
            if available <= 0:
                continue
            eligible = await queue.eligible_count()
            spawn_count = min(available, eligible)
            for _ in range(spawn_count):
                self._spawn(provider)
                await asyncio.sleep(0)

    def _spawn(self, provider: AufProvider) -> None:
        self._sequence += 1
        worker_id = f"auf-{provider.value}-{self._sequence}"
        queue = self._queues[provider]
        worker = self._worker_class(
            bot=self._bot,
            queue=queue,
            client=self._client,
            executor=AIRequestExecutor(self._usage_service),
            pricing=self._pricing,
            usd_to_rub=self._usd_to_rub,
            worker_id=worker_id,
        )
        task = asyncio.create_task(
            worker.process_once(),
            name=f"{worker_id}:generation",
        )
        self._active[provider].add(task)

    def _drop_finished(self) -> None:
        for provider, tasks in self._active.items():
            finished = {task for task in tasks if task.done()}
            tasks.difference_update(finished)
            for task in finished:
                if task.cancelled():
                    continue
                error = task.exception()
                if error is None:
                    continue
                logger.error(
                    "Auf generation task escaped worker boundary provider=%s: %s",
                    provider,
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )

    async def _runtime_settings(self):
        now = time.monotonic()
        if (
            self._settings is None
            or now - self._settings_loaded_at >= _SETTINGS_CACHE_SECONDS
        ):
            self._settings = await self._runtime.runtime_settings()
            self._settings_loaded_at = now
        return self._settings


__all__ = (
    "AufGenerationDispatcher",
    "ProviderAwareKieClient",
)
