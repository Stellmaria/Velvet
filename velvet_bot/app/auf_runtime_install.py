from __future__ import annotations

import importlib
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.ai_usage import build_ai_usage_service
from velvet_bot.domains.auf_runtime import (
    AufGenerationDispatcher,
    AufRuntimeRepository,
)
from velvet_bot.domains.auf_runtime.cancellable_worker import (
    build_cancellable_worker_class,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.infrastructure.ai import KieClient
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback
from velvet_bot.workers import PeriodicWorkerSpec

_INSTALLED = False


def _remove_legacy_media_workers(manager: Any) -> None:
    names = tuple(
        name
        for name in manager.registered_names()
        if name.startswith("kie-media-generation")
    )
    for name in names:
        manager._specs.pop(name, None)
        manager._snapshots.pop(name, None)
        manager._run_locks.pop(name, None)


def install_auf_runtime_dispatcher() -> None:
    """Replace fixed Kie slots with the database-driven Auf dispatcher."""

    global _INSTALLED
    if _INSTALLED:
        return

    workers = importlib.import_module("velvet_bot.app.workers")
    bootstrap = importlib.import_module("velvet_bot.app.bootstrap")
    original = workers.build_worker_manager

    def build_worker_manager_with_auf_runtime(*args: Any, **kwargs: Any):
        manager = original(*args, **kwargs)
        kie_settings = kwargs.get("kie_settings") or load_kie_settings()
        if not kie_settings.enabled:
            return manager

        database = kwargs.get("database")
        bot = kwargs.get("bot")
        if database is None or bot is None:
            raise RuntimeError("Динамический диспетчер Ауф требует bot и database.")
        usage_service = kwargs.get("ai_usage_service") or build_ai_usage_service(
            database=database
        )
        if kie_settings.api_key is None:
            raise RuntimeError("Ауф включён без KIE_API_KEY.")

        _remove_legacy_media_workers(manager)
        client = KieClient(
            api_key=kie_settings.api_key,
            models=kie_settings.models,
            base_url=kie_settings.base_url,
            file_upload_base_url=kie_settings.file_upload_base_url,
            grs_api_key=kie_settings.grs_api_key,
            grs_base_url=kie_settings.grs_base_url,
            timeout_seconds=kie_settings.timeout_seconds,
            poll_interval_seconds=kie_settings.poll_interval_seconds,
            task_timeout_seconds=kie_settings.task_timeout_seconds,
        )
        dispatcher = AufGenerationDispatcher(
            bot=bot,
            database=database,
            client=client,
            usage_service=usage_service,
            pricing=kie_settings.pricing,
            usd_to_rub=kie_settings.usd_to_rub,
            max_attempts=kie_settings.generation_max_attempts,
            worker_class=build_cancellable_worker_class(
                workers.KieGenerationWorker
            ),
        )
        manager.register(
            PeriodicWorkerSpec(
                name="auf-generation-dispatcher",
                description=(
                    "Динамическая очередь Kie/GRS · Стэл 100 · пространство до 20"
                ),
                interval_seconds=1,
                runner=dispatcher.run,
            )
        )

        runtime_store = AufRuntimeRepository(database)

        async def notify_initial_setup() -> None:
            if not await runtime_store.claim_setup_notice():
                return
            await bot.send_message(
                GLOBAL_WORKSPACE_CREATOR_ID,
                "<b>⚙️ Первичная настройка Ауф</b>\n\n"
                "Динамический диспетчер включён. Стартовые пределы: "
                "<b>Kie 100</b>, <b>GRS 100</b>, пространство <b>5</b> с возможностью "
                "увеличения до <b>20</b>.\n\n"
                "Откройте управление, проверьте значения и подтвердите настройку.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Открыть параллельность Ауф",
                                callback_data=AufCallback(
                                    action="runtime",
                                    workspace_id=DEFAULT_WORKSPACE_ID,
                                ).pack(),
                            )
                        ]
                    ]
                ),
            )

        manager.register(
            PeriodicWorkerSpec(
                name="auf-runtime-setup-notice",
                description="Однократное подтверждение лимитов Ауф",
                interval_seconds=86400,
                runner=notify_initial_setup,
            )
        )
        return manager

    workers.build_worker_manager = build_worker_manager_with_auf_runtime
    bootstrap.build_worker_manager = build_worker_manager_with_auf_runtime
    _INSTALLED = True


__all__ = ("install_auf_runtime_dispatcher",)
