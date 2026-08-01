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
from .hermes_incident import HermesIncident, HermesIncidentClient, redact_sensitive
from .krita_process import KritaProcessManager
from .models import OperationState, utc_now
from .polling_log_filter import install_supervisor_polling_filter
from .runtime import OperationConflict, VelvetSupervisor as BaseVelvetSupervisor

install_supervisor_polling_filter()
logger = logging.getLogger(__name__)


class VelvetSupervisor(BaseVelvetSupervisor):
    """Supervisor runtime extended with Krita and bounded Hermes escalation."""

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.krita = KritaProcessManager(
            project_dir=settings.project_dir,
            runtime_dir=settings.runtime_dir,
        )
        self.hermes_incidents = HermesIncidentClient(
            enabled=settings.hermes_incident_enabled,
            base_url=settings.hermes_base_url,
            api_key=settings.hermes_api_key,
            timeout_seconds=settings.hermes_timeout_seconds,
            cooldown_seconds=settings.hermes_cooldown_seconds,
            max_log_chars=settings.hermes_max_log_chars,
            result_callback=self._on_hermes_incident_result,
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
        payload["hermes_incidents"] = self.hermes_incidents.status()
        return payload

    def _on_hermes_incident_result(self, report: dict[str, Any]) -> None:
        run_id = str(report.get("run_id") or "unknown")
        status = str(report.get("status") or "unknown")
        output = redact_sensitive(str(report.get("output") or "[empty]"))[-3000:]
        level = "INFO" if status == "completed" else "ERROR"
        self._notifier.send(
            "Hermes завершил разбор инцидента",
            f"run_id={run_id}\nstatus={status}\n\n{output}",
            level=level,
        )

    def _register_crash_locked(self) -> float | None:
        restart_delay = super()._register_crash_locked()
        restart_count = len(self._restart_times)
        should_escalate = (
            self.settings.hermes_incident_enabled
            and (
                self._crash_loop_open
                or restart_count >= self.settings.hermes_escalate_after_restarts
            )
        )
        if should_escalate:
            incident = HermesIncident(
                service="velvet-bot",
                reason=(
                    "crash-loop-open"
                    if self._crash_loop_open
                    else "repeated-process-exit"
                ),
                exit_code=self._last_exit_code,
                restart_count=restart_count,
                crash_loop_open=self._crash_loop_open,
                log_tail="\n".join(list(self._tail)[-80:]),
                git_head=None,
                branch=None,
            )
            if self.hermes_incidents.submit_async(incident):
                logger.warning(
                    "Submitted Velvet crash incident to Hermes restarts=%s crash_loop=%s",
                    restart_count,
                    self._crash_loop_open,
                )
        return restart_delay

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
        """Hand off self-control through a short Task Scheduler wrapper.

        A plain restart intentionally bypasses the shared operation lock. It is the
        recovery path when a console command or another worker has wedged that
        lock. Self-update remains serialized because changing the checkout while
        another operation is active is unsafe.
        """

        lock_acquired = False
        if update:
            if not self._operation_lock.acquire(blocking=False):
                raise OperationConflict("Уже выполняется другая системная операция.")
            lock_acquired = True

        kind = "supervisor-update" if update else "supervisor-restart"
        operation = OperationState.create(
            kind,
            "Self-update передан bootstrap-задаче."
            if update
            else "Аварийный перезапуск передан bootstrap-задаче; активная операция будет прервана.",
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
            if lock_acquired:
                self._operation_lock.release()


__all__ = ("OperationConflict", "VelvetSupervisor")
