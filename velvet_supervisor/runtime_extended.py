from __future__ import annotations

import logging
import os
from typing import Any

from .bootstrap_launcher import launch_bootstrap_short
from .dependencies import (
    DependencySyncError,
    sync_current_requirements,
    sync_remote_requirements,
)
from .krita_process import KritaProcessManager
from .models import OperationState, utc_now
from .polling_log_filter import install_supervisor_polling_filter
from .runtime import OperationConflict, VelvetSupervisor as BaseVelvetSupervisor

install_supervisor_polling_filter()
logger = logging.getLogger(__name__)


class VelvetSupervisor(BaseVelvetSupervisor):
    """Supervisor runtime extended with on-demand Krita process ownership."""

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.krita = KritaProcessManager(
            project_dir=settings.project_dir,
            runtime_dir=settings.runtime_dir,
        )

    def start(self) -> None:
        try:
            result = sync_current_requirements(self.settings)
            if result.installed:
                logger.info(
                    "Supervisor dependencies synchronized source=%s sha=%s",
                    result.source,
                    result.requirements_sha256[:12],
                )
        except DependencySyncError as error:
            # The control plane must still come online so the owner can inspect
            # logs and retry. Optional features report their own missing package.
            logger.exception("Could not synchronize Supervisor dependencies")
            self._notifier.send(
                "Зависимости Supervisor не установлены",
                str(error)[-3000:],
                level="ERROR",
            )

        self.krita.start()
        try:
            super().start()
        except Exception:
            self.krita.shutdown()
            raise

    def shutdown(self) -> None:
        self.krita.shutdown()
        super().shutdown()

    def status(self) -> dict[str, Any]:
        payload = super().status()
        payload["krita"] = self.krita.status()
        return payload

    def ensure_krita(self) -> dict[str, Any]:
        return self.krita.ensure()

    def touch_krita(self) -> dict[str, Any]:
        return self.krita.touch()

    def stop_krita(self, *, force: bool = False) -> dict[str, Any]:
        return self.krita.stop(force=force)

    def krita_status(self) -> dict[str, Any]:
        return self.krita.status()

    def _update_operation(self, operation: OperationState) -> dict[str, Any]:
        dependency_result = sync_remote_requirements(self.settings)
        result = super()._update_operation(operation)
        result["dependency_sync"] = dependency_result.to_dict()
        return result

    def schedule_supervisor_restart(self, *, update: bool) -> OperationState:
        """Hand off self-restart through a short Task Scheduler wrapper."""

        if not self._operation_lock.acquire(blocking=False):
            raise OperationConflict("Уже выполняется другая системная операция.")
        kind = "supervisor-update" if update else "supervisor-restart"
        operation = OperationState.create(
            kind,
            "Self-update передан bootstrap-задаче."
            if update
            else "Перезапуск передан bootstrap-задаче.",
        )
        operation.status = "handed-off"
        operation.started_at = utc_now()
        with self._lock:
            process = self._process
            bot_pid = process.pid if process is not None and process.poll() is None else None
            self._last_operation = operation
        try:
            dependency_result = (
                sync_remote_requirements(self.settings) if update else None
            )
            launch = launch_bootstrap_short(
                self.settings,
                action="update" if update else "restart",
                operation_id=operation.id,
                supervisor_pid=os.getpid(),
                bot_pid=bot_pid,
            )
            operation.result = launch.to_dict()
            if dependency_result is not None:
                operation.result["dependency_sync"] = dependency_result.to_dict()
            self._persist_operation(operation)
            return operation
        except Exception:
            operation.status = "error"
            operation.finished_at = utc_now()
            self._persist_operation(operation)
            raise
        finally:
            self._operation_lock.release()


__all__ = ("OperationConflict", "VelvetSupervisor")
