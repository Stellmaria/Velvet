#!/usr/bin/env python3
"""Launcher-backed coder runtime with explicit workspace and execution evidence."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from codex_first_runner import Handler, ThreadingHTTPServer
from codex_first_safe_runner import primary_execution_started
from codex_launcher_runner import LauncherTierProviderManager
from codex_tier_runner import AuditedTierProviderManager


def execution_started_from_evidence(
    record: dict[str, Any], stdout: str = ""
) -> bool:
    """Derive execution without treating lifecycle output as mutation evidence."""

    last_event = record.get("last_event")
    event_started = (
        isinstance(last_event, dict) and last_event.get("execution_started") is True
    )
    return bool(
        record.get("execution_started") is True
        or record.get("primary_output_started") is True
        or record.get("provider_output_started") is True
        or event_started
        or primary_execution_started(stdout)
    )


class ContextLauncherTierProviderManager(LauncherTierProviderManager):
    """Add trusted runtime evidence without replacing the existing Git audit."""

    def _prepare_workspace(self, run_id: str) -> tuple[Path, str]:
        target, source_ref = super()._prepare_workspace(run_id)
        self.store.update(
            run_id,
            process_cwd=str(target),
            execution_started=False,
            push_or_pr_observed=False,
        )
        return target, source_ref

    def _run_once(self, run_id: str, model: str, prompt: str) -> dict[str, Any]:
        result = super()._run_once(run_id, model, prompt)
        if self._started(result):
            self.store.update(run_id, execution_started=True)
        return result

    def _provider_run(
        self,
        run_id: str,
        prompt: str,
        model: str,
    ) -> dict[str, Any]:
        result = super()._provider_run(run_id, prompt, model)
        if self._started(result):
            self.store.update(run_id, execution_started=True)
        return result

    def _success(
        self,
        run_id: str,
        model: str,
        models: list[str],
        routes: list[str],
        route: str,
        reason: str | None,
        stdout: str,
    ) -> None:
        final_branch = self._snapshot(self.workspace)["branch"]
        execution_started = execution_started_from_evidence(
            self.store.read(run_id), stdout
        )
        super()._success(run_id, model, models, routes, route, reason, stdout)
        execution_started = execution_started or execution_started_from_evidence(
            self.store.read(run_id), stdout
        )
        self.store.update(
            run_id,
            final_branch=final_branch,
            execution_started=execution_started,
        )


def build_manager() -> AuditedTierProviderManager:
    backend = os.environ.get("CODEX_EXECUTION_BACKEND", "launcher").strip()
    if backend == "launcher":
        return ContextLauncherTierProviderManager()
    if backend == "local" and os.environ.get("HERMES_ALLOW_LOCAL_ROLLBACK") == "1":
        # Explicit operator rollback only. Canonical Compose never sets this gate.
        return AuditedTierProviderManager()
    raise RuntimeError(
        "CODEX_EXECUTION_BACKEND должен быть launcher; local требует "
        "HERMES_ALLOW_LOCAL_ROLLBACK=1"
    )


def main() -> int:
    manager = build_manager()
    host = os.environ.get("CODEX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("CODEX_RUNNER_PORT", "8642"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("CODEX_RUNNER_PORT должен быть от 1024 до 65535")
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet context-aware launcher runner listening on {host}:{port}; "
        f"backend={os.environ.get('CODEX_EXECUTION_BACKEND', 'launcher')}; "
        f"default={manager.default_model}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
