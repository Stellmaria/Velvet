from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from velvet_bot.ai_jobs import AIJob, AIJobRepository
from velvet_bot.ai_jobs_ui import build_job_detail_text, build_job_keyboard
from velvet_bot.database import Database


@dataclass(slots=True)
class AIJobTracker:
    repository: AIJobRepository
    message: Message
    job_id: int
    created_by: int | None

    @classmethod
    async def create(
        cls,
        *,
        database: Database,
        source_message: Message,
        kind: str,
        title: str,
        provider: str | None,
        model: str | None,
        request_payload: dict[str, Any] | None = None,
    ) -> "AIJobTracker":
        created_by = source_message.from_user.id if source_message.from_user else None
        repository = AIJobRepository(database)
        job_id = await repository.create(
            kind=kind,
            title=title,
            provider=provider,
            model=model,
            request_payload=request_payload,
            created_by=created_by,
        )
        job = await repository.get(job_id, created_by=created_by)
        if job is None:
            raise RuntimeError("AI-задание создано, но не найдено в журнале.")
        status_message = await source_message.answer(
            build_job_detail_text(job),
            reply_markup=build_job_keyboard(job),
        )
        return cls(
            repository=repository,
            message=status_message,
            job_id=job_id,
            created_by=created_by,
        )

    async def _get(self) -> AIJob:
        job = await self.repository.get(self.job_id, created_by=self.created_by)
        if job is None:
            raise RuntimeError("AI-задание больше не найдено в журнале.")
        return job

    async def _edit(self, job: AIJob) -> None:
        try:
            await self.message.edit_text(
                build_job_detail_text(job),
                reply_markup=build_job_keyboard(job),
            )
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                raise

    async def stage(self, stage: str) -> None:
        await self.repository.mark_stage(self.job_id, stage)
        await self._edit(await self._get())

    async def ready(
        self,
        *,
        result_text: str,
        result_payload: dict[str, Any] | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> None:
        await self.repository.mark_ready(
            self.job_id,
            result_text=result_text,
            result_payload=result_payload,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        await self._edit(await self._get())

    async def error(self, error: BaseException | str) -> None:
        await self.repository.mark_error(self.job_id, error)
        await self._edit(await self._get())


__all__ = ("AIJobTracker",)
