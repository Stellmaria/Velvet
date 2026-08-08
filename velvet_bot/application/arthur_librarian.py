from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp
import asyncpg

from velvet_bot.application.storage_librarian import (
    LibrarianReportPublisher,
    StorageLibrarianService,
)
from velvet_bot.core.config.arthur import ArthurSettings
from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.arthur_repository import (
    ArthurStorageLibrarianRepository,
)
from velvet_bot.domains.telegram_storage.librarian_models import (
    LibrarianObject,
    StorageLibrarianError,
    StorageLibrarianSettings,
    UnsupportedStorageContent,
)
from velvet_bot.infrastructure.ai.storage_librarian_hermes import HermesRunsClient
from velvet_bot.infrastructure.ai.storage_librarian_ollama import (
    OllamaStorageAnalysisClient,
)
from velvet_bot.infrastructure.telegram.arthur_storage_gateway import (
    ArthurStorageGatewayClient,
)

logger = logging.getLogger(__name__)
_ARCHIVE_BATCH_SIZE = 1


@dataclass(frozen=True, slots=True)
class ArthurAnalysisOutcome:
    object_id: int
    job: dict[str, object] | None
    analysis: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class ArthurArchiveStatus:
    active: bool
    stopping: bool
    counts: dict[str, int]
    analyzer_version: str
    last_error: str | None


@dataclass(frozen=True, slots=True)
class ArthurServiceHealth:
    gateway: bool
    ollama: bool
    text_model: bool
    hermes: bool


class ArthurStorageLibrarianService(StorageLibrarianService):
    def __init__(
        self,
        *,
        database: Database,
        settings: StorageLibrarianSettings,
        object_loader: ArthurStorageGatewayClient,
        analysis_client: OllamaStorageAnalysisClient,
        answer_client: HermesRunsClient,
        report_publisher: LibrarianReportPublisher,
        target_object_id: int | None,
    ) -> None:
        super().__init__(
            database=database,
            settings=settings,
            object_loader=object_loader,
            analysis_client=analysis_client,
            answer_client=answer_client,
            report_publisher=report_publisher,
        )
        self.repository = ArthurStorageLibrarianRepository(
            database,
            target_object_id=target_object_id,
        )


class ArthurLibrarianApplication:
    def __init__(
        self,
        *,
        settings: ArthurSettings,
        librarian_settings: StorageLibrarianSettings,
        database: Database,
        report_publisher: LibrarianReportPublisher,
    ) -> None:
        self.settings = settings
        self.librarian_settings = librarian_settings
        self.database = database
        self.repository = ArthurStorageLibrarianRepository(database)
        gateway_credential = settings.storage_gateway_api_key
        self.gateway = ArthurStorageGatewayClient(
            base_url=settings.storage_gateway_base_url,
            credential=gateway_credential,
            timeout_seconds=librarian_settings.run_timeout_seconds,
        )
        self._report_publisher = report_publisher
        self._analysis_lock = asyncio.Lock()
        self._archive_control_lock = asyncio.Lock()
        self._archive_stop_event = asyncio.Event()
        self._archive_task: asyncio.Task[None] | None = None
        self._archive_last_error: str | None = None

    def _service(
        self,
        *,
        target_object_id: int | None = None,
    ) -> StorageLibrarianService:
        return ArthurStorageLibrarianService(
            database=self.database,
            settings=self.librarian_settings,
            object_loader=self.gateway,
            analysis_client=OllamaStorageAnalysisClient(self.librarian_settings),
            answer_client=HermesRunsClient(self.librarian_settings),
            report_publisher=self._report_publisher,
            target_object_id=target_object_id,
        )

    async def _ollama_health(self) -> tuple[bool, bool]:
        timeout = aiohttp.ClientTimeout(total=5)
        url = self.librarian_settings.ollama_base_url.rstrip("/") + "/api/tags"
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return False, False
                    payload: object = await response.json(content_type=None)
        except (asyncio.TimeoutError, aiohttp.ClientError, ValueError):
            return False, False
        if not isinstance(payload, dict):
            return True, False
        models = payload.get("models")
        if not isinstance(models, list):
            return True, False
        names = {
            str(item.get("name") or item.get("model") or "")
            for item in models
            if isinstance(item, dict)
        }
        return True, self.librarian_settings.text_model in names

    async def _hermes_health(self) -> bool:
        timeout = aiohttp.ClientTimeout(total=5)
        url = self.librarian_settings.hermes_base_url.rstrip("/") + "/health"
        credential = self.librarian_settings.hermes_api_key
        headers = {"Authorization": f"Bearer {credential}"} if credential else {}
        try:
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            ) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return False
                    payload: object = await response.json(content_type=None)
        except (asyncio.TimeoutError, aiohttp.ClientError, ValueError):
            return False
        return isinstance(payload, dict) and payload.get("status") == "ok"

    async def service_health(self) -> ArthurServiceHealth:
        gateway, ollama_state, hermes = await asyncio.gather(
            self.gateway.health(),
            self._ollama_health(),
            self._hermes_health(),
        )
        ollama, text_model = ollama_state
        return ArthurServiceHealth(
            gateway=gateway,
            ollama=ollama,
            text_model=text_model,
            hermes=hermes,
        )

    async def analyze(self, object_id: int) -> ArthurAnalysisOutcome:
        if not self.librarian_settings.enabled:
            raise StorageLibrarianError("Storage Librarian disabled.")
        async with self._analysis_lock:
            queued = await self.repository.enqueue_object(
                object_id,
                settings=self.librarian_settings,
                priority=1_000_000,
            )
            if not queued:
                raise StorageLibrarianError(
                    f"Storage #{object_id} unavailable or running."
                )
            processed = await self._service(
                target_object_id=object_id
            ).process_once(auto_enqueue=False)
            if not processed:
                raise StorageLibrarianError(
                    f"Storage #{object_id} could not be claimed for manual analysis."
                )
        return ArthurAnalysisOutcome(
            object_id=object_id,
            job=await self.repository.job_status(object_id),
            analysis=await self.repository.analysis_by_object_id(object_id),
        )

    async def _archive_loop(self, stop_event: asyncio.Event) -> None:
        service = self._service()
        try:
            async with self.repository.full_archive_phase():
                while not stop_event.is_set():
                    try:
                        queued = await self.repository.enqueue_pending(
                            settings=self.librarian_settings,
                            limit=_ARCHIVE_BATCH_SIZE,
                        )
                        if stop_event.is_set():
                            break
                        async with self._analysis_lock:
                            if stop_event.is_set():
                                break
                            processed = await service.process_once(auto_enqueue=False)
                        self._archive_last_error = None
                        if queued or processed:
                            logger.info(
                                "Arthur archive cycle queued=%s processed=%s analyzer=%s",
                                queued,
                                processed,
                                self.librarian_settings.analyzer_version,
                            )
                    except asyncio.CancelledError:
                        raise
                    except (
                        StorageLibrarianError,
                        asyncpg.PostgresError,
                        aiohttp.ClientError,
                        OSError,
                        ValueError,
                        TimeoutError,
                    ) as error:
                        self._archive_last_error = str(error)[:1200] or type(error).__name__
                        logger.warning("Arthur archive cycle failed: %s", error)
                    if stop_event.is_set():
                        break
                    try:
                        await asyncio.wait_for(
                            stop_event.wait(),
                            timeout=self.librarian_settings.scan_interval_seconds,
                        )
                    except TimeoutError:
                        pass
        except StorageLibrarianError as error:
            self._archive_last_error = str(error)[:1200] or type(error).__name__
            logger.warning("Arthur archive phase failed: %s", error)
        finally:
            async with self._archive_control_lock:
                if self._archive_task is asyncio.current_task():
                    self._archive_task = None

    async def start_archive(self) -> bool:
        if not self.librarian_settings.enabled:
            raise StorageLibrarianError("Storage Librarian disabled.")
        async with self._archive_control_lock:
            task = self._archive_task
            if task is not None and not task.done():
                return False
            stop_event = asyncio.Event()
            self._archive_stop_event = stop_event
            self._archive_last_error = None
            self._archive_task = asyncio.create_task(
                self._archive_loop(stop_event),
                name="arthur-full-archive",
            )
            return True

    async def stop_archive(self) -> bool:
        async with self._archive_control_lock:
            task = self._archive_task
            if task is None or task.done():
                return False
            self._archive_stop_event.set()
            return True

    async def archive_status(self) -> ArthurArchiveStatus:
        async with self._archive_control_lock:
            task = self._archive_task
            active = task is not None and not task.done()
            stopping = active and self._archive_stop_event.is_set()
            last_error = self._archive_last_error
        return ArthurArchiveStatus(
            active=active,
            stopping=stopping,
            counts=await self.repository.counts(),
            analyzer_version=self.librarian_settings.analyzer_version,
            last_error=last_error,
        )

    async def shutdown(self) -> None:
        async with self._archive_control_lock:
            task = self._archive_task
            if task is None or task.done():
                return
            self._archive_stop_event.set()
        await task

    async def result(self, object_id: int) -> ArthurAnalysisOutcome:
        return ArthurAnalysisOutcome(
            object_id=object_id,
            job=await self.repository.job_status(object_id),
            analysis=await self.repository.analysis_by_object_id(object_id),
        )

    async def queue_counts(self) -> dict[str, int]:
        return await self.repository.counts()

    async def digest(self, days: int) -> list[dict[str, object]]:
        return await self.repository.recent_analyses(days=days, limit=12)

    async def ask(self, question: str) -> str:
        return await self._service().answer(question)

    async def download(self, object_id: int) -> tuple[LibrarianObject, bytes]:
        item = await self.repository.load_object(object_id)
        if item is None:
            raise StorageLibrarianError(f"Storage #{object_id} not found.")
        if (
            item.encrypted
            or item.storage_kind not in self.librarian_settings.allowed_kinds
            or item.size_bytes > self.librarian_settings.max_object_bytes
        ):
            raise UnsupportedStorageContent(
                f"Storage #{object_id} is protected or outside Arthur limits."
            )
        payload = await self.gateway.download(
            item,
            max_bytes=self.librarian_settings.max_object_bytes,
        )
        return item, payload


__all__ = (
    "ArthurAnalysisOutcome",
    "ArthurArchiveStatus",
    "ArthurLibrarianApplication",
    "ArthurServiceHealth",
    "ArthurStorageLibrarianService",
)
