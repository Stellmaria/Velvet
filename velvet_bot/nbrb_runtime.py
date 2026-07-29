from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

_INSTALLED = False
_ORIGINAL_BUILD_WORKER_MANAGER = None


def _enabled() -> bool:
    return os.getenv("KIE_NBRB_RATE_ENABLED", "true").strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "нет",
    }


def _timeout_seconds() -> int:
    try:
        value = int(os.getenv("KIE_NBRB_TIMEOUT_SECONDS", "20").strip())
    except (AttributeError, TypeError, ValueError):
        value = 20
    return max(5, min(value, 120))


def install_nbrb_exchange_rate() -> None:
    """Add one persisted NBRB check per Minsk calendar day to the worker registry."""

    global _INSTALLED, _ORIGINAL_BUILD_WORKER_MANAGER
    if _INSTALLED:
        return

    import velvet_bot.app.workers as workers_module
    from velvet_bot.domains.media_generation.worker import KieGenerationWorker
    from velvet_bot.services.nbrb_exchange_rate import (
        DailyNbrbExchangeRateService,
        NbrbExchangeRateRepository,
        NbrbRateClient,
    )
    from velvet_bot.workers import PeriodicWorkerSpec

    _ORIGINAL_BUILD_WORKER_MANAGER = workers_module.build_worker_manager

    def build_worker_manager_with_nbrb(*args: Any, **kwargs: Any):
        manager = _ORIGINAL_BUILD_WORKER_MANAGER(*args, **kwargs)
        if not _enabled() or "kie-nbrb-exchange-rate" in manager.registered_names():
            return manager

        database = kwargs.get("database")
        if database is None:
            return manager

        kie_workers: list[KieGenerationWorker] = []
        for name, spec in manager._specs.items():
            if not name.startswith("kie-media-generation"):
                continue
            worker = getattr(spec.runner, "__self__", None)
            if isinstance(worker, KieGenerationWorker):
                kie_workers.append(worker)
        if not kie_workers:
            return manager

        def apply_usd_to_rub(value: Decimal) -> None:
            if value <= 0:
                return
            for worker in kie_workers:
                worker._usd_to_rub = value

        service = DailyNbrbExchangeRateService(
            repository=NbrbExchangeRateRepository(database),
            client=NbrbRateClient(
                base_url=os.getenv("KIE_NBRB_BASE_URL", "https://api.nbrb.by"),
                timeout_seconds=_timeout_seconds(),
            ),
            timezone_name=os.getenv("KIE_NBRB_TIMEZONE", "Europe/Minsk"),
            on_rate=apply_usd_to_rub,
        )
        manager.register(
            PeriodicWorkerSpec(
                name="kie-nbrb-exchange-rate",
                description="Ежедневный официальный курс USD/RUB по НБРБ",
                interval_seconds=3600,
                runner=service.process_once,
            )
        )
        return manager

    workers_module.build_worker_manager = build_worker_manager_with_nbrb
    _INSTALLED = True


__all__ = ("install_nbrb_exchange_rate",)
