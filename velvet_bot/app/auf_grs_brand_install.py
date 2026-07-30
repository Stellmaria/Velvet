from __future__ import annotations

import importlib
import re
from html import escape
from typing import Any

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

import velvet_bot.app.grs_resilience as grs_resilience
from velvet_bot.app.grs_campaign_retry import CampaignGrsGenerationWorker
from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import KieGenerationRequest
from velvet_bot.domains.media_generation.worker import (
    KieGenerationWorker as BaseKieGenerationWorker,
)

_INSTALLED = False
_PRIVATE_LINE_PATTERNS = (
    r"(?mi)^Провайдер:\s*.*(?:\n|$)",
    r"(?mi)^Задача(?:\s+провайдера)?:\s*.*(?:\n|$)",
    r"(?mi)^Баланс\s+(?:GRS|Kie)(?:\s+после\s+остановки)?:.*(?:\n|$)",
    r"(?mi)^Ожидаемая стоимость:.*(?:\n|$)",
    r"(?mi)^Ожидаемое списание:.*(?:\n|$)",
    r"(?mi)^Расчётная себестоимость.*(?:\n|$)",
    r"(?mi)^Стоимость остатка:.*(?:\n|$)",
    r"(?mi)^Себестоимость списаний:.*(?:\n|$)",
    r"(?mi)^Расчёт себестоимости:.*(?:\n|$)",
    r"(?mi)^Последние списания Kie.*(?:\n|$)",
    r"(?mi)^(?:Попытка|Повтор):.*(?:\n|$)",
    r"(?mi)^Ошибка доставки:.*(?:\n|$)",
    r"(?mi)^Причина GRS AI:.*(?:\n|$)",
    r"(?mi)^NSFW checker Kie:.*(?:\n|$)",
)


def _sanitize_auf_text(text: str) -> str:
    """Convert internal generation copy into stable product-facing language."""

    cleaned = str(text)
    cleaned = re.sub(
        r"(?m)^Контент: <b>Mature</b>(?: · модерация GRS активна)?\n?",
        "",
        cleaned,
    )
    legacy_queue = (
        "Задача поставлена в очередь. Worker скачает выбранные Telegram-фото, "
        "временно загрузит их в Kie и только затем вызовет модель."
    )
    cleaned = cleaned.replace(
        legacy_queue,
        "Задача поставлена в очередь. Референсы будут подготовлены перед генерацией.",
    )
    legacy_mature_paragraph = (
        "Mature-режим включён. Для Seedream бот передаст документированный "
        "<code>nsfw_checker=false</code>. У Nano Banana Pro отдельного API-флага "
        "отключения фильтра нет, поэтому действует политика самого провайдера."
    )
    cleaned = cleaned.replace(
        legacy_mature_paragraph,
        "После выбора модели будут показаны доступные варианты качества.",
    )
    cleaned = cleaned.replace("Изменить Kie", "Основные модели")
    cleaned = cleaned.replace("Изменить GRS", "Nano Banana")
    cleaned = cleaned.replace("Kie.ai:", "Основные модели:")
    cleaned = cleaned.replace("GRS AI:", "Nano Banana:")
    cleaned = cleaned.replace(
        "Глобальные пределы Kie и GRS управляются Стэл.",
        "Глобальные пределы управляются Стэл.",
    )
    cleaned = cleaned.replace(
        "Kie.ai выключен на сервере.",
        "Генерация сейчас недоступна.",
    )
    cleaned = cleaned.replace(
        "GRS AI не настроен на сервере.",
        "Этот режим генерации сейчас недоступен.",
    )
    cleaned = cleaned.replace(
        "Nano Banana 2/Pro требуют GRS_API_KEY на сервере.",
        "Эти модели сейчас недоступны.",
    )
    cleaned = re.sub(
        r"(?mi)Неверный model id[^\n]*",
        "Модель временно недоступна из-за ошибки настройки.",
        cleaned,
    )
    cleaned = re.sub(
        r"\b(?:KIE|GRS)_[A-Z0-9_]+\b",
        "внутренняя настройка",
        cleaned,
    )
    cleaned = re.sub(
        r"https?://[^\s<>]*(?:kie\.ai|grsai\.com)[^\s<>]*",
        "[внутренний адрес скрыт]",
        cleaned,
        flags=re.IGNORECASE,
    )
    for pattern in _PRIVATE_LINE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)

    provider_forms = {
        "через Kie.ai": "через сервис генерации",
        "через GRS AI": "через сервис генерации",
        "в Kie": "на обработку",
        "из Kie": "из сервиса генерации",
        "GRS AI": "сервис генерации",
        "Kie.ai": "сервис генерации",
        "провайдеру": "сервису генерации",
        "провайдером": "сервисом генерации",
        "провайдера": "сервиса генерации",
        "провайдер": "сервис генерации",
    }
    for old, new in provider_forms.items():
        cleaned = cleaned.replace(old, new)

    cleaned = (
        cleaned.replace("🐈 <b>Мяу</b>", "🐕 <b>Ауф</b>")
        .replace("🐈 Мяу", "🐕 Ауф")
        .replace("МЯУ", "АУФ")
        .replace("Мяу", "Ауф")
        .replace("мяу", "ауф")
        .replace("MEOW", "AUF")
        .replace("Meow", "Auf")
    )
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _sanitize_keyboard(markup: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    rows = []
    for row in markup.inline_keyboard:
        updated = []
        for button in row:
            text = _sanitize_auf_text(button.text)
            copy_method = getattr(button, "model_copy", None)
            if copy_method is None:
                copy_method = button.copy
            updated.append(copy_method(update={"text": text}))
        rows.append(updated)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _public_failure_reason(error: BaseException) -> str:
    text = str(error or "").casefold()
    if any(word in text for word in ("violation", "moderation", "safety", "policy")):
        return "Запрос не прошёл автоматическую проверку содержимого."
    if any(
        word in text
        for word in (
            "timeout",
            "timed out",
            "network",
            "connection",
            "disconnect",
            "недоступ",
            "соединен",
            "таймаут",
        )
    ):
        return "Сервис генерации временно не ответил."
    return "Во время генерации произошла внутренняя ошибка."


def _wrap_text_function(module: Any, name: str) -> None:
    original = getattr(module, name, None)
    if not callable(original) or getattr(original, "__auf_privacy_wrapped__", False):
        return

    def wrapped(*args: Any, **kwargs: Any) -> str:
        return _sanitize_auf_text(original(*args, **kwargs))

    wrapped.__auf_privacy_wrapped__ = True  # type: ignore[attr-defined]
    setattr(module, name, wrapped)


def _wrap_keyboard_function(module: Any, name: str) -> None:
    original = getattr(module, name, None)
    if not callable(original) or getattr(original, "__auf_privacy_wrapped__", False):
        return

    def wrapped(*args: Any, **kwargs: Any) -> InlineKeyboardMarkup:
        return _sanitize_keyboard(original(*args, **kwargs))

    wrapped.__auf_privacy_wrapped__ = True  # type: ignore[attr-defined]
    setattr(module, name, wrapped)


def _wrap_runtime_text(module: Any) -> None:
    original = getattr(module, "_runtime_text", None)
    if not callable(original) or getattr(original, "__auf_privacy_wrapped__", False):
        return

    async def wrapped(*args: Any, **kwargs: Any):
        text, global_owner, configured = await original(*args, **kwargs)
        return _sanitize_auf_text(text), global_owner, configured

    wrapped.__auf_privacy_wrapped__ = True  # type: ignore[attr-defined]
    module._runtime_text = wrapped


def _wrap_progress_method(cls: type[Any]) -> None:
    original = getattr(cls, "_friendly_progress_text", None)
    if not callable(original) or getattr(original, "__auf_privacy_wrapped__", False):
        return

    def wrapped(
        self: Any,
        *,
        task: AITask,
        request: KieGenerationRequest,
        percent: int,
        stage: str,
    ) -> str:
        return _sanitize_auf_text(
            original(
                self,
                task=task,
                request=request,
                percent=percent,
                stage=stage,
            )
        )

    wrapped.__auf_privacy_wrapped__ = True  # type: ignore[attr-defined]
    cls._friendly_progress_text = wrapped  # type: ignore[method-assign]


def _install_terminal_failure_guard(cls: type[Any]) -> None:
    if not hasattr(cls, "_notify_terminal_failure_best_effort"):
        return

    async def notify(self: Any, task: AITask, error: Exception) -> None:
        try:
            chat_id = int(task.payload.get("chat_id") or 0)
        except (TypeError, ValueError):
            chat_id = 0
        if chat_id <= 0:
            return
        try:
            await self._bot.send_message(
                chat_id,
                "<b>Ауф не смог завершить генерацию</b>\n\n"
                f"{escape(_public_failure_reason(error))}\n"
                "Повторная платная отправка автоматически не выполнялась.",
            )
        except TelegramAPIError:
            return
        finally:
            balances = getattr(self, "_provider_balances", None)
            if isinstance(balances, dict):
                balances.pop(str(task.id), None)

    cls._notify_terminal_failure_best_effort = notify  # type: ignore[method-assign]


def _install_router_privacy() -> None:
    runtime = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_auf_runtime"
    )
    _wrap_runtime_text(runtime)
    _wrap_keyboard_function(runtime, "_runtime_keyboard")

    provider_balance = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_auf_grs_balance"
    )
    _wrap_text_function(provider_balance, "_render_grs_balance")
    _wrap_keyboard_function(provider_balance, "build_grs_balance_keyboard")

    legacy_balance = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_auf_balance"
    )
    _wrap_text_function(legacy_balance, "_render_balance")
    _wrap_keyboard_function(legacy_balance, "build_kie_balance_keyboard")

    photo = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_auf"
    )
    for name in (
        "_model_selection_text",
        "_reference_collection_text",
        "format_request_review",
        "_quality_selection_text",
    ):
        _wrap_text_function(photo, name)

    photo_models = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_auf_grs"
    )
    _wrap_text_function(photo_models, "model_selection_text")

    video = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_auf_video_simple"
    )
    for name in ("_model_text", "_settings_text", "_review_text"):
        _wrap_text_function(video, name)

    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    for name in ("_user_settings_text", "_task_line"):
        _wrap_text_function(portal, name)

    delivery = importlib.import_module("velvet_bot.app.auf_result_delivery_recovery")
    _wrap_text_function(delivery, "_result_caption")

    from velvet_bot import workspace_ui
    from velvet_bot.domains.auf_runtime import AUF_MODULE_KEY

    workspace_ui.MODULE_HELP[AUF_MODULE_KEY] = (
        "Создание изображений и видео. Владелец пространства управляет доступом, "
        "балансом и числом одновременных задач."
    )


def install_auf_grs_brand() -> None:
    """Install the final product-facing privacy layer for the Auf module."""

    global _INSTALLED
    if _INSTALLED:
        return

    grs_resilience._sanitize_meow_text = _sanitize_auf_text
    grs_resilience._sanitize_auf_text = _sanitize_auf_text

    workers_module = importlib.import_module("velvet_bot.app.workers")
    worker_classes: list[type[Any]] = [
        FriendlyKieGenerationWorker,
        BaseKieGenerationWorker,
        grs_resilience.ResilientFriendlyKieGenerationWorker,
        CampaignGrsGenerationWorker,
    ]
    active_worker = getattr(workers_module, "KieGenerationWorker", None)
    if isinstance(active_worker, type):
        worker_classes.append(active_worker)

    seen: set[type[Any]] = set()
    for worker_class in worker_classes:
        if worker_class in seen:
            continue
        seen.add(worker_class)
        _wrap_progress_method(worker_class)
        _install_terminal_failure_guard(worker_class)

    _install_router_privacy()
    _INSTALLED = True


__all__ = (
    "_public_failure_reason",
    "_sanitize_auf_text",
    "install_auf_grs_brand",
)
