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
from velvet_bot.infrastructure.media_delivery_runtime import (
    MediaDeliveryRuntime,
    ensure_media_delivery_runtime,
)

from .economy_worker import KieGenerationWorker as EconomyKieGenerationWorker
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
    """Provider-aware generation worker with canonical durable delivery."""

    def __init__(
        self,
        *,
        media_delivery_runtime: MediaDeliveryRuntime | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        runtime = media_delivery_runtime or ensure_media_delivery_runtime(
            bot=self._bot,
            database=self._queue.database,
            provider_client=self._client,
        )
        self._media_delivery_runtime = runtime
        self._queue.configure_durable_delivery(
            resolver=runtime.resolver,
            delivery=runtime.delivery,
        )
        self._provider_balances: dict[str, Decimal | None] = {}

    def __getattribute__(self, name: str) -> Any:
        if name == "_deliver_best_effort":
            # Compatibility installers may still assign this method to subclasses.
            # Delivery ownership is deliberately non-overridable during migration.
            return object.__getattribute__(self, "_durable_delivery_guard")
        return super().__getattribute__(name)

    async def process_once(self) -> bool:
        await self._recover_durable_delivery(phase="before-generation")
        processed = await super().process_once()
        if processed:
            # A provider may finish without URLs in the first success payload, or
            # durable registration may need the now-committed ai_tasks row. Run the
            # task-independent recovery immediately instead of waiting for the next
            # periodic tick while the user sees a completed progress message.
            await self._recover_durable_delivery(phase="after-generation")
        return processed

    async def _recover_durable_delivery(self, *, phase: str) -> None:
        try:
            await self._media_delivery_runtime.recover_once()
        except Exception as error:  # p2-approved-boundary: isolate-durable-recovery-tick
            from velvet_bot.application.media_delivery import (
                classify_media_delivery_error,
                raise_if_programming_error,
            )

            failure = classify_media_delivery_error(
                error,
                phase=f"durable_recovery_{phase}",
            )
            logger.error(
                "durable_media_recovery_failed phase=%s code=%s fingerprint=%s",
                phase,
                failure.code,
                failure.fingerprint,
            )
            raise_if_programming_error(
                error,
                phase=f"durable_recovery_{phase}",
            )

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

    async def _durable_delivery_guard(
        self,
        *,
        chat_id: int | None,
        request: KieGenerationRequest,
        record: KieTaskRecord,
    ) -> None:
        """Generation workers never deliver; the durable use case owns that phase."""

        del chat_id, request, record



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
    from velvet_bot.app.media_delivery_ui_install import install_media_delivery_ui

    install_media_delivery_ui()
    _disable_legacy_delivery_installers()
    _INSTALLED = True


def _disable_legacy_delivery_installers() -> None:
    """Keep old composition stages inert while deployments migrate safely."""

    for module_name in (
        "velvet_bot.app.original_image_delivery_hotfix",
        "velvet_bot.app.original_video_delivery_hotfix",
        "velvet_bot.app.auf_result_delivery_recovery",
        "velvet_bot.app.auf_active_delivery_fix",
    ):
        module = importlib.import_module(module_name)
        if hasattr(module, "_INSTALLED"):
            module._INSTALLED = True


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
