from __future__ import annotations

import importlib
import logging
from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from typing import Any

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from velvet_bot.domains.ai_usage import AITask
from velvet_bot.infrastructure.ai import KieError

from .economy_worker import KieGenerationWorker as EconomyKieGenerationWorker
from .file_delivery_worker import result_filename
from .models import KieGenerationRequest, KieModelAlias, KieTaskRecord
from .worker import ProgressMessage, optional_int, render_progress_bar

logger = logging.getLogger(__name__)
_INSTALLED = False
_MONEY_QUANTUM = Decimal("0.01")
_GRS_CREDITS = {
    KieModelAlias.NANO_BANANA_2: Decimal("1200"),
    KieModelAlias.NANO_BANANA_PRO: Decimal("1800"),
}


class FriendlyKieGenerationWorker(EconomyKieGenerationWorker):
    """Render provider-aware progress while retaining the durable economy queue."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._provider_balances: dict[str, Decimal | None] = {}

    async def _start_progress(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest,
    ) -> ProgressMessage | None:
        chat_id = optional_int(task.payload.get("chat_id"))
        if chat_id is None:
            return None

        balance: Decimal | None = None
        if request.model.is_grs:
            try:
                balance = await self._client.get_grs_credits()
            except KieError:
                logger.info("Could not load GRS balance for progress task=%s", task.id)
        self._provider_balances[str(task.id)] = balance

        stage = "Задача принята. Готовлю всё для генерации."
        text = self._friendly_progress_text(
            task=task,
            request=request,
            percent=0,
            stage=stage,
        )
        try:
            message = await self._bot.send_message(chat_id, text)
        except TelegramAPIError:
            logger.exception("Could not create friendly progress message for %s", task.id)
            return None
        return ProgressMessage(
            chat_id=chat_id,
            message_id=optional_int(getattr(message, "message_id", None)),
            last_percent=0,
            last_stage=stage,
        )

    async def _publish_progress(
        self,
        progress: ProgressMessage | None,
        *,
        task: AITask,
        request: KieGenerationRequest,
        percent: int,
        stage: str,
        force: bool = False,
    ) -> None:
        if progress is None:
            return
        safe_percent = max(0, min(100, int(percent)))
        normalized_stage = friendly_stage(request, stage)
        if (
            not force
            and safe_percent == progress.last_percent
            and normalized_stage == progress.last_stage
        ):
            return
        text = self._friendly_progress_text(
            task=task,
            request=request,
            percent=safe_percent,
            stage=normalized_stage,
        )
        try:
            if progress.message_id is None:
                message = await self._bot.send_message(progress.chat_id, text)
                progress.message_id = optional_int(
                    getattr(message, "message_id", None)
                )
            else:
                await self._bot.edit_message_text(
                    text,
                    chat_id=progress.chat_id,
                    message_id=progress.message_id,
                )
            progress.last_percent = safe_percent
            progress.last_stage = normalized_stage
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                logger.warning(
                    "Could not update friendly progress message for %s: %s",
                    task.id,
                    error,
                )
        except TelegramAPIError:
            logger.exception("Could not update friendly progress message for %s", task.id)

    def _friendly_progress_text(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest,
        percent: int,
        stage: str,
    ) -> str:
        provider = "GRS AI" if request.model.is_grs else "Kie.ai"
        estimated_usd = self._pricing.estimate_usd(request)
        estimated_rub = self._pricing.estimate_rub(
            request,
            usd_to_rub=self._usd_to_rub,
        )
        attempt_label = (
            f"Повтор: <b>{task.attempt_count}/{task.max_attempts}</b>"
            if task.attempt_count > 1
            else f"Попытка: <b>{task.attempt_count}/{task.max_attempts}</b>"
        )
        finance_lines = [
            f"Ожидаемая стоимость: <b>${_money(estimated_usd)} · "
            f"{_money(estimated_rub)} ₽</b>"
        ]
        expected_credits = _GRS_CREDITS.get(request.model)
        if expected_credits is not None:
            finance_lines[0] = (
                f"Ожидаемое списание: <b>≈ {_credits(expected_credits)} кредитов · "
                f"${_money(estimated_usd)} · {_money(estimated_rub)} ₽</b>"
            )
            balance = self._provider_balances.get(str(task.id))
            if balance is None:
                finance_lines.append("Баланс GRS: <b>не удалось проверить</b>")
            else:
                remaining = max(Decimal("0"), balance - expected_credits)
                finance_lines.append(
                    f"Баланс GRS: <b>{_credits(balance)}</b> кредитов "
                    f"· после запуска ≈ <b>{_credits(remaining)}</b>"
                )

        safe_percent = max(0, min(100, int(percent)))
        return (
            f"<b>Мяу создаёт · {escape(request.model.display_name)}</b>\n\n"
            f"<code>{render_progress_bar(safe_percent)}</code> <b>{safe_percent}%</b>\n"
            f"✨ {escape(friendly_stage(request, stage))}\n\n"
            f"Провайдер: <b>{provider}</b>\n"
            f"Режим: <b>{escape(request.input_mode.display_name)}</b>\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Референсы: <b>{len(request.references)}</b>\n"
            f"Контент: <b>{escape(request.content_mode.display_name)}</b>\n\n"
            + "\n".join(finance_lines)
            + "\n\n"
            f"{attempt_label}\n"
            f"Задача: <code>{task.id}</code>"
        )

    async def _notify_terminal_failure_best_effort(
        self,
        task: AITask,
        error: Exception,
    ) -> None:
        chat_id = optional_int(task.payload.get("chat_id"))
        if chat_id is None:
            return
        request = _request_from_payload(task.payload)
        message = friendly_error(request, str(error))
        provider = "GRS AI" if request is not None and request.model.is_grs else "Kie.ai"
        try:
            await self._bot.send_message(
                chat_id,
                "<b>Мяу не смог завершить генерацию</b>\n\n"
                f"Провайдер: <b>{provider}</b>\n"
                f"{escape(message)}\n\n"
                "Повторная платная отправка автоматически не выполнялась.\n"
                f"Задача: <code>{task.id}</code>",
            )
        except TelegramAPIError:
            logger.exception("Could not deliver friendly terminal failure for %s", task.id)
        finally:
            self._provider_balances.pop(str(task.id), None)

    async def _deliver_best_effort(
        self,
        *,
        chat_id: int | None,
        request: KieGenerationRequest,
        record: KieTaskRecord,
    ) -> None:
        """Download provider results and send both preview and original file."""
        if chat_id is None:
            return
        provider = "GRS AI" if request.model.is_grs else "Kie.ai"
        media_name = "Видео" if request.model.is_video else "Изображение"
        caption = (
            f"<b>Мяу · {escape(request.model.display_name)}</b>\n"
            f"Провайдер: <b>{provider}</b>\n"
            f"{media_name}: <b>готово</b>\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Референсов: <b>{len(request.references)}</b>\n"
            f"Контент: <b>{escape(request.content_mode.display_name)}</b>\n"
            f"Задача провайдера: <code>{escape(record.task_id)}</code>\n\n"
            f"Результат скачан ботом напрямую с {provider}. Ниже отправлены "
            "предпросмотр и оригинальный файл."
        )
        try:
            if not record.result_urls:
                await self._send_telegram_with_retry(
                    "empty result notice",
                    lambda: self._bot.send_message(
                        chat_id,
                        caption + f"\n\n{provider} завершил задачу без URL результата.",
                    ),
                )
                return
            for index, url in enumerate(record.result_urls, start=1):
                item_caption = caption if index == 1 else None
                result = await self._download_result(url)
                filename = result_filename(
                    url=url,
                    provider_task_id=record.task_id,
                    index=index,
                    mime_type=result.mime_type,
                    video=request.model.is_video,
                )
                if request.model.is_video:
                    await self._send_video_and_document(
                        chat_id=chat_id,
                        payload=result.payload,
                        filename=filename,
                        caption=item_caption,
                    )
                else:
                    await self._send_image_and_document(
                        chat_id=chat_id,
                        payload=result.payload,
                        filename=filename,
                        caption=item_caption,
                    )
        except TelegramAPIError:
            logger.exception(
                "%s task %s succeeded but Telegram file delivery failed",
                provider,
                record.task_id,
            )
        except (RuntimeError, ValueError, OSError):
            logger.exception(
                "%s task %s succeeded but original result download failed",
                provider,
                record.task_id,
            )


def friendly_stage(request: KieGenerationRequest, stage: str) -> str:
    text = str(stage or "").strip()
    if not request.model.is_grs:
        return text.replace("worker-ом", "обработчиком")
    exact = {
        "Экономная кампания взята worker-ом.": "Задача принята. Подготавливаю генерацию.",
        "Подготовка сохранённого референса.": "Проверяю и подготавливаю референсы.",
        "Kie завершил генерацию.": "GRS AI завершил генерацию.",
        "Kie сообщил об ошибке генерации.": "GRS AI сообщил об ошибке генерации.",
        "Задача ожидает вычислительных ресурсов Kie.": "Задача ожидает свободные ресурсы GRS AI.",
        "Kie готовит задачу к генерации.": "GRS AI готовит задачу к генерации.",
    }
    if text in exact:
        return exact[text]
    text = text.replace(
        "Используем уже загруженный референс Kie без повторной загрузки.",
        "Использую уже подготовленные референсы без повторной загрузки.",
    )
    text = text.replace("createTask", "запрос GRS AI")
    text = text.replace("Kie.ai", "GRS AI")
    text = text.replace("Kie-кампании", "GRS-генерации")
    text = text.replace("Kie ", "GRS AI ")
    text = text.replace("Экономная кампания", "Безопасная генерация")
    text = text.replace("worker-ом", "обработчиком")
    return text


def friendly_error(
    request: KieGenerationRequest | None,
    message: str,
) -> str:
    text = str(message or "").strip()
    if request is None or not request.model.is_grs:
        return text
    if "Ответ createTask потерян или не подтверждён" in text:
        return (
            "GRS AI не подтвердил приём задачи. Статус первой отправки неизвестен, "
            "поэтому автоматический платный повтор остановлен, чтобы исключить двойное списание."
        )
    return friendly_stage(request, text)


def install_friendly_media_worker() -> None:
    """Install the provider-aware worker in the application composition root."""

    global _INSTALLED
    if _INSTALLED:
        return
    workers = importlib.import_module("velvet_bot.app.workers")
    workers.KieGenerationWorker = FriendlyKieGenerationWorker
    _INSTALLED = True


def _request_from_payload(payload: Mapping[str, object]) -> KieGenerationRequest | None:
    value = payload.get("request")
    if not isinstance(value, Mapping):
        return None
    try:
        return KieGenerationRequest.from_task_payload(value)
    except ValueError:
        return None


def _money(value: Decimal) -> str:
    return format(value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f").replace(
        ".", ","
    )


def _credits(value: Decimal) -> str:
    integral = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(integral):,}".replace(",", " ")


__all__ = (
    "FriendlyKieGenerationWorker",
    "friendly_error",
    "friendly_stage",
    "install_friendly_media_worker",
)
