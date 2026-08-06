from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile
from PIL import Image, ImageFilter, ImageOps

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITaskQueueService
from velvet_bot.domains.media_generation import KieReferenceImage

CODEX_IMAGE_TASK_TYPE = "media.generate.codex_image"
GPT_IMAGE_2_ALIAS = "gpt_image_2"
GPT_IMAGE_2_NAME = "GPT Image 2"
CODEX_IMAGE_MODELS = (
    ("gpt-5.6-sol", "GPT-5.6 Sol"),
    ("gpt-5.6-terra", "GPT-5.6 Terra"),
    ("gpt-5.6-luna", "GPT-5.6 Luna"),
)
CODEX_IMAGE_EFFORTS = (
    ("low", "Низкое"),
    ("medium", "Среднее"),
    ("high", "Высокое"),
    ("xhigh", "Очень высокое"),
    ("max", "Максимальное"),
)
CODEX_IMAGE_RESOLUTIONS = ("1K", "2K", "4K")
CODEX_IMAGE_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9")
MAX_CODEX_IMAGE_REFERENCES = 5
MAX_CODEX_IMAGE_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_CODEX_IMAGE_PROMPT = 8000
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CodexImageRequest:
    prompt: str
    references: tuple[KieReferenceImage, ...]
    input_mode: str
    aspect_ratio: str
    resolution: str
    analysis_model: str
    reasoning_effort: str

    def __post_init__(self) -> None:
        if not self.prompt.strip() or len(self.prompt.strip()) > MAX_CODEX_IMAGE_PROMPT:
            raise ValueError("Промт GPT Image 2 должен содержать от 1 до 8000 символов.")
        if self.input_mode not in {"text", "photo_text"}:
            raise ValueError("Неизвестный режим GPT Image 2.")
        if self.input_mode == "text" and self.references:
            raise ValueError("В режиме «Только текст» референсы не используются.")
        if self.input_mode == "photo_text" and not 1 <= len(self.references) <= MAX_CODEX_IMAGE_REFERENCES:
            raise ValueError("В режиме «Фото + текст» требуется от 1 до 5 референсов.")
        if self.aspect_ratio not in CODEX_IMAGE_RATIOS:
            raise ValueError("Недоступное соотношение сторон GPT Image 2.")
        if self.resolution not in CODEX_IMAGE_RESOLUTIONS:
            raise ValueError("Недоступный размер GPT Image 2.")
        if self.analysis_model not in {item[0] for item in CODEX_IMAGE_MODELS}:
            raise ValueError("Недоступная модель анализа GPT Image 2.")
        if self.reasoning_effort not in {item[0] for item in CODEX_IMAGE_EFFORTS}:
            raise ValueError("Недоступное усилие анализа GPT Image 2.")

    def to_payload(self) -> dict[str, object]:
        return {
            "prompt": self.prompt.strip(),
            "references": [item.to_payload() for item in self.references],
            "input_mode": self.input_mode,
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "analysis_model": self.analysis_model,
            "reasoning_effort": self.reasoning_effort,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "CodexImageRequest":
        raw_refs = payload.get("references")
        references = (
            tuple(KieReferenceImage.from_payload(item) for item in raw_refs if isinstance(item, Mapping))
            if isinstance(raw_refs, (list, tuple))
            else ()
        )
        return cls(
            prompt=str(payload.get("prompt") or "").strip(),
            references=references,
            input_mode=str(payload.get("input_mode") or "text").strip(),
            aspect_ratio=str(payload.get("aspect_ratio") or "9:16").strip(),
            resolution=str(payload.get("resolution") or "2K").strip().upper(),
            analysis_model=str(payload.get("analysis_model") or "gpt-5.6-terra").strip(),
            reasoning_effort=str(payload.get("reasoning_effort") or "high").strip(),
        )


class CodexImageClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("CODEX_IMAGE_ROUTER_URL", "http://hermes-coder-router:8878").strip().rstrip("/")
        self.token = os.getenv("CODEX_IMAGE_ROUTER_TOKEN", "").strip()
        self.timeout_seconds = max(120, int(os.getenv("CODEX_IMAGE_TIMEOUT_SECONDS", "3600")))
        if not self.base_url:
            raise RuntimeError("CODEX_IMAGE_ROUTER_URL не задан.")
        if len(self.token) < 24:
            raise RuntimeError("CODEX_IMAGE_ROUTER_TOKEN отсутствует или слишком короткий.")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def submit(self, request: CodexImageRequest, references: list[dict[str, object]], *, session_id: str) -> str:
        payload = {
            "prompt": request.prompt,
            "references": references,
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
            "analysis_model": request.analysis_model,
            "reasoning_effort": request.reasoning_effort,
            "session_id": session_id,
        }
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
            async with session.post(f"{self.base_url}/v1/coders/velvet/images", json=payload) as response:
                data = await self._json(response)
        run_id = str(data.get("run_id") or "").strip()
        if len(run_id) != 32:
            raise RuntimeError("Codex GPT Image 2 не вернул run_id.")
        return run_id

    async def status(self, run_id: str) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
            async with session.get(f"{self.base_url}/v1/coders/velvet/images/{run_id}") as response:
                return await self._json(response)

    async def content(self, run_id: str) -> bytes:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
            async with session.get(f"{self.base_url}/v1/coders/velvet/images/{run_id}/content") as response:
                if response.status >= 400:
                    details = (await response.text())[:2000]
                    raise RuntimeError(f"GPT Image 2 content HTTP {response.status}: {details}")
                payload = await response.read()
        if not payload or len(payload) > 50 * 1024 * 1024:
            raise RuntimeError("GPT Image 2 вернул пустой или слишком большой файл.")
        return payload

    @staticmethod
    async def _json(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            data = await response.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError) as error:
            raise RuntimeError(f"GPT Image 2 router вернул повреждённый ответ HTTP {response.status}.") from error
        if response.status >= 400:
            raise RuntimeError(str(data.get("error") or f"GPT Image 2 HTTP {response.status}"))
        if not isinstance(data, dict):
            raise RuntimeError("GPT Image 2 router вернул неожиданный ответ.")
        return data


def export_dimensions(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    edge = {"1K": 1024, "2K": 2048, "4K": 3840}[resolution.upper()]
    left, right = (int(value) for value in aspect_ratio.split(":", 1))
    if left >= right:
        width, height = edge, max(2, round(edge * right / left))
    else:
        width, height = max(2, round(edge * left / right)), edge
    return width - width % 2, height - height % 2


def export_jpeg(payload: bytes, *, resolution: str, aspect_ratio: str) -> tuple[bytes, tuple[int, int]]:
    target = export_dimensions(resolution, aspect_ratio)
    with Image.open(io.BytesIO(payload)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        upscaled = image.width < target[0] or image.height < target[1]
        image = ImageOps.fit(image, target, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        if upscaled:
            image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=3))
        destination = io.BytesIO()
        image.save(destination, format="JPEG", quality=95, subsampling=0, optimize=True, progressive=True)
    return destination.getvalue(), target


def preview_jpeg(payload: bytes, *, max_edge: int = 1600) -> bytes:
    with Image.open(io.BytesIO(payload)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        destination = io.BytesIO()
        image.save(destination, format="JPEG", quality=88, optimize=True, progressive=True)
    return destination.getvalue()


def _remaining_percent(window: object) -> float | None:
    if not isinstance(window, Mapping):
        return None
    try:
        used = float(window.get("used_percent"))
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, 100.0 - used))


def _limit_line(before: object, after: object, label: str, key: str) -> str:
    before_value = _remaining_percent(before.get(key) if isinstance(before, Mapping) else None)
    after_value = _remaining_percent(after.get(key) if isinstance(after, Mapping) else None)
    if before_value is None and after_value is None:
        return f"{label}: недоступно"
    if before_value is None:
        return f"{label}: {after_value:.1f}% осталось"
    if after_value is None:
        return f"{label}: {before_value:.1f}% до запуска"
    return f"{label}: {before_value:.1f}% → {after_value:.1f}% ({after_value - before_value:+.1f} п.п.)"


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_clock(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone(timezone.utc).strftime("%H:%M:%S UTC")


def _format_duration(value: object) -> str:
    try:
        total = max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return "—"
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} ч {minutes} мин {seconds} сек"
    if minutes:
        return f"{minutes} мин {seconds} сек"
    return f"{seconds} сек"


def _seconds_between(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, int(round((end - start).total_seconds())))


def _progress_bar(progress: int) -> str:
    bounded = max(0, min(100, int(progress)))
    filled = min(10, max(0, round(bounded / 10)))
    return "█" * filled + "░" * (10 - filled)


def render_codex_image_progress(
    request: CodexImageRequest,
    *,
    task_id: object,
    progress: int,
    stage: str,
    queued_at: datetime,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    rate_limits_before: object = None,
    rate_limits_after: object = None,
) -> str:
    bounded = max(0, min(100, int(progress)))
    current = finished_at or datetime.now(timezone.utc)
    queue_wait = _seconds_between(queued_at, started_at)
    execution = _seconds_between(started_at, current)
    total = _seconds_between(queued_at, current) if started_at is not None else None
    primary = _limit_line(
        rate_limits_before,
        rate_limits_after,
        "Короткое окно",
        "primary",
    )
    secondary = _limit_line(
        rate_limits_before,
        rate_limits_after,
        "Недельное окно",
        "secondary",
    )
    if bounded == 0 and rate_limits_before is None and rate_limits_after is None:
        primary = "Короткое окно: снимок при запуске"
        secondary = "Недельное окно: снимок при запуске"
    lines = [
        f"<b>Ауф · {GPT_IMAGE_2_NAME}</b>",
        "",
        f"Статус: <b>{escape(stage)} · {bounded}%</b>",
        f"<code>{_progress_bar(bounded)}</code>",
        "",
        f"Экспорт: <b>{request.resolution} JPEG · {request.aspect_ratio}</b>",
        f"Референсов: <b>{len(request.references)}</b>",
        "",
        "<b>Лимит Codex</b>",
        primary,
        secondary,
        "",
        "<b>Время</b>",
        f"Поставлено: <code>{_format_clock(queued_at)}</code>",
        f"Старт: <code>{_format_clock(started_at)}</code>",
        f"Завершено: <code>{_format_clock(finished_at)}</code>",
    ]
    if started_at is None:
        lines.append("В очереди: <b>ожидание запуска</b>")
    else:
        lines.extend(
            [
                f"В очереди: <b>{_format_duration(queue_wait)}</b>",
                f"Выполнение: <b>{_format_duration(execution)}</b>",
                f"Всего: <b>{_format_duration(total)}</b>",
            ]
        )
    if task_id:
        lines.extend(("", f"Задача: <code>{escape(str(task_id))}</code>"))
    return "\n".join(lines)


class CodexImageWorker:
    def __init__(self, *, bot: Bot, queue: AITaskQueueService, client: CodexImageClient, worker_id: str = "codex-image-generation") -> None:
        self._bot = bot
        self._queue = queue
        self._client = client
        self._worker_id = worker_id

    async def process_once(self) -> int:
        task = await self._queue.claim_next(
            worker_id=self._worker_id,
            scopes=(AIBudgetScope.VISION,),
            task_types=(CODEX_IMAGE_TASK_TYPE,),
        )
        if task is None:
            return 0
        chat_id = _optional_int(task.payload.get("chat_id"))
        message_id = _optional_int(task.payload.get("progress_message_id"))
        started_at = datetime.now(timezone.utc)
        queued_at = (
            _parse_timestamp(task.payload.get("queued_at"))
            or _parse_timestamp(task.created_at)
            or started_at
        )
        request: CodexImageRequest | None = None
        status: dict[str, Any] = {}
        try:
            request = CodexImageRequest.from_payload(
                _mapping(task.payload.get("request"))
            )
            initial = render_codex_image_progress(
                request,
                task_id=task.id,
                progress=5,
                stage="подготовка референсов",
                queued_at=queued_at,
                started_at=started_at,
            )
            if message_id is None:
                message_id = await self._progress(chat_id, initial)
            else:
                await self._edit_progress(chat_id, message_id, initial)
            refs = await self._download_references(request)
            await self._edit_progress(
                chat_id,
                message_id,
                render_codex_image_progress(
                    request,
                    task_id=task.id,
                    progress=20,
                    stage="анализ и генерация",
                    queued_at=queued_at,
                    started_at=started_at,
                ),
            )
            run_id = await self._client.submit(
                request,
                refs,
                session_id=f"auf-{task.id}",
            )
            status = await self._wait(
                task.id,
                run_id,
                chat_id,
                message_id,
                request=request,
                queued_at=queued_at,
                started_at=started_at,
            )
            await self._edit_progress(
                chat_id,
                message_id,
                render_codex_image_progress(
                    request,
                    task_id=task.id,
                    progress=92,
                    stage="получение результата",
                    queued_at=queued_at,
                    started_at=started_at,
                    rate_limits_before=status.get("rate_limits_before"),
                    rate_limits_after=status.get("rate_limits_after"),
                ),
            )
            original = await self._client.content(run_id)
            await self._edit_progress(
                chat_id,
                message_id,
                render_codex_image_progress(
                    request,
                    task_id=task.id,
                    progress=96,
                    stage="подготовка JPEG",
                    queued_at=queued_at,
                    started_at=started_at,
                    rate_limits_before=status.get("rate_limits_before"),
                    rate_limits_after=status.get("rate_limits_after"),
                ),
            )
            exported, dimensions = await asyncio.to_thread(
                export_jpeg,
                original,
                resolution=request.resolution,
                aspect_ratio=request.aspect_ratio,
            )
            preview = await asyncio.to_thread(preview_jpeg, exported)
            finished_at = datetime.now(timezone.utc)
            queue_wait_seconds = _seconds_between(queued_at, started_at) or 0
            execution_seconds = _seconds_between(started_at, finished_at) or 0
            total_seconds = _seconds_between(queued_at, finished_at) or 0
            result: dict[str, object] = {
                "provider": "codex_subscription",
                "model_alias": GPT_IMAGE_2_ALIAS,
                "analysis_model": request.analysis_model,
                "reasoning_effort": request.reasoning_effort,
                "reference_count": len(request.references),
                "prompt_chars": len(request.prompt),
                "resolution": request.resolution,
                "aspect_ratio": request.aspect_ratio,
                "width": dimensions[0],
                "height": dimensions[1],
                "output_format": "jpeg",
                "output_bytes": len(exported),
                "provider_run_id": run_id,
                "rate_limits_before": status.get("rate_limits_before"),
                "rate_limits_after": status.get("rate_limits_after"),
                "usage": status.get("usage"),
                "queued_at": queued_at.isoformat(),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "queue_wait_seconds": queue_wait_seconds,
                "execution_seconds": execution_seconds,
                "total_seconds": total_seconds,
                "generation_attempts": 1,
            }
            await self._queue.complete(
                task_id=task.id,
                worker_id=self._worker_id,
                result=result,
            )
            await self._edit_progress(
                chat_id,
                message_id,
                render_codex_image_progress(
                    request,
                    task_id=task.id,
                    progress=100,
                    stage="завершено",
                    queued_at=queued_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    rate_limits_before=status.get("rate_limits_before"),
                    rate_limits_after=status.get("rate_limits_after"),
                ),
            )
            await self._deliver(chat_id, request, result, preview, exported)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary: isolate-codex-image-task-failure
            await self._queue.fail(
                task_id=task.id,
                worker_id=self._worker_id,
                error=error,
                base_delay_seconds=0,
                max_delay_seconds=0,
            )
            if request is not None:
                finished_at = datetime.now(timezone.utc)
                await self._edit_progress(
                    chat_id,
                    message_id,
                    render_codex_image_progress(
                        request,
                        task_id=task.id,
                        progress=0,
                        stage="ошибка",
                        queued_at=queued_at,
                        started_at=started_at,
                        finished_at=finished_at,
                        rate_limits_before=status.get("rate_limits_before"),
                        rate_limits_after=status.get("rate_limits_after"),
                    ),
                )
            await self._notify_failure(chat_id, error)
        return 1

    async def _download_references(self, request: CodexImageRequest) -> list[dict[str, object]]:
        values: list[dict[str, object]] = []
        for index, reference in enumerate(request.references, start=1):
            destination = io.BytesIO()
            await self._bot.download(reference.telegram_file_id, destination=destination, timeout=90, seek=True)
            payload = destination.getvalue()
            if not payload or len(payload) > MAX_CODEX_IMAGE_REFERENCE_BYTES:
                raise ValueError("Референс GPT Image 2 пуст или превышает 10 МБ.")
            values.append(
                {
                    "file_name": Path(reference.file_name or f"reference-{index}.jpg").name,
                    "mime_type": reference.mime_type,
                    "data_base64": base64.b64encode(payload).decode("ascii"),
                }
            )
        return values

    async def _wait(
        self,
        task_id: UUID,
        run_id: str,
        chat_id: int | None,
        message_id: int | None,
        *,
        request: CodexImageRequest,
        queued_at: datetime,
        started_at: datetime,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + self._client.timeout_seconds
        progress = 20
        while True:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("GPT Image 2 превысил время ожидания.")
            status = await self._client.status(run_id)
            state = str(status.get("status") or "")
            if state == "completed":
                return status
            if state in {"failed", "cancelled"}:
                raise RuntimeError(
                    str(status.get("error") or f"GPT Image 2: {state}")
                )
            progress = min(90, progress + 3)
            await self._edit_progress(
                chat_id,
                message_id,
                render_codex_image_progress(
                    request,
                    task_id=task_id,
                    progress=progress,
                    stage="анализ и генерация",
                    queued_at=queued_at,
                    started_at=started_at,
                    rate_limits_before=status.get("rate_limits_before"),
                    rate_limits_after=status.get("rate_limits_after"),
                ),
            )
            await self._queue.heartbeat(
                task_id=task_id,
                worker_id=self._worker_id,
            )
            await asyncio.sleep(5)

    async def _deliver(
        self,
        chat_id: int | None,
        request: CodexImageRequest,
        result: Mapping[str, object],
        preview: bytes,
        document: bytes,
    ) -> None:
        if chat_id is None:
            return
        model_name = dict(CODEX_IMAGE_MODELS).get(request.analysis_model, request.analysis_model)
        effort_name = dict(CODEX_IMAGE_EFFORTS).get(request.reasoning_effort, request.reasoning_effort)
        before, after = result.get("rate_limits_before"), result.get("rate_limits_after")
        caption = "\n".join(
            (
                f"<b>Ауф · {GPT_IMAGE_2_NAME}</b>",
                f"Анализ: <b>{escape(model_name)} · {escape(effort_name)}</b>",
                f"Референсов: <b>{len(request.references)}</b>",
                f"Экспорт: <b>{request.resolution} JPEG · {result['width']}×{result['height']}</b>",
                "Генераций: <b>1</b>",
                "",
                "<b>Лимит Codex</b>",
                _limit_line(before, after, "Короткое окно", "primary"),
                _limit_line(before, after, "Недельное окно", "secondary"),
                "",
                "<b>Время</b>",
                f"В очереди: <b>{_format_duration(result.get('queue_wait_seconds'))}</b>",
                f"Выполнение: <b>{_format_duration(result.get('execution_seconds'))}</b>",
                f"Всего: <b>{_format_duration(result.get('total_seconds'))}</b>",
            )
        )
        await self._bot.send_photo(
            chat_id,
            photo=BufferedInputFile(preview, filename="gpt-image-2-preview.jpg"),
            caption=caption,
        )
        await self._bot.send_document(
            chat_id,
            document=BufferedInputFile(document, filename=f"gpt-image-2-{request.resolution.casefold()}.jpg"),
            caption="Оригинальный JPEG-файл без Telegram-сжатия.\n\n" + caption,
        )

    async def _progress(self, chat_id: int | None, text: str) -> int | None:
        if chat_id is None:
            return None
        try:
            message = await self._bot.send_message(chat_id, text)
            return _optional_int(getattr(message, "message_id", None))
        except TelegramAPIError:
            return None

    async def _edit_progress(self, chat_id: int | None, message_id: int | None, text: str) -> None:
        if chat_id is None or message_id is None:
            return
        try:
            await self._bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                logger.warning("Could not update GPT Image 2 progress: %s", error)
        except TelegramAPIError:
            logger.exception("Could not update GPT Image 2 progress")

    async def _notify_failure(self, chat_id: int | None, error: BaseException) -> None:
        if chat_id is None:
            return
        try:
            await self._bot.send_message(
                chat_id,
                f"<b>GPT Image 2 завершился ошибкой.</b>\n\n{escape(str(error)[:3000])}\n\nАвтоматическая повторная генерация не выполнялась.",
            )
        except TelegramAPIError:
            logger.exception("Could not report GPT Image 2 failure")


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _optional_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = (
    "CODEX_IMAGE_EFFORTS",
    "CODEX_IMAGE_MODELS",
    "CODEX_IMAGE_RATIOS",
    "CODEX_IMAGE_RESOLUTIONS",
    "CODEX_IMAGE_TASK_TYPE",
    "CodexImageClient",
    "CodexImageRequest",
    "CodexImageWorker",
    "GPT_IMAGE_2_ALIAS",
    "GPT_IMAGE_2_NAME",
    "MAX_CODEX_IMAGE_PROMPT",
    "MAX_CODEX_IMAGE_REFERENCES",
    "export_dimensions",
    "export_jpeg",
    "render_codex_image_progress",
)
