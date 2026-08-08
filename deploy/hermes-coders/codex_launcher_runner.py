#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from codex_first_runner import Handler, ThreadingHTTPServer
from codex_first_safe_runner import primary_execution_started
from codex_tier_runner import AuditedTierProviderManager
from sandbox_launcher_client import LauncherClientError, SandboxLauncherClient

_PROJECTS = frozenset({"velvet", "max"})
_TERMINAL = frozenset({"completed", "failed", "cancelled"})


def sandbox_visible_prompt(prompt: str, controller_workspace: Path) -> str:
    """Translate only the injected controller workspace notice for the sandbox."""

    controller_notice = (
        f"EFFECTIVE RUN WORKSPACE: {controller_workspace}\n"
        "This current working directory is the only task checkout. "
        "Do not access /workspace, /workspace-base, chat workspaces or sibling runs."
    )
    sandbox_notice = (
        "EFFECTIVE RUN WORKSPACE: /workspace\n"
        "This current working directory is the only task checkout. "
        "Do not access /workspace-base, chat workspaces or sibling runs."
    )
    return prompt.replace(controller_notice, sandbox_notice)


class LauncherTierProviderManager(AuditedTierProviderManager):
    """Preserve the existing control plane and replace only Codex process launch."""

    def __init__(self) -> None:
        super().__init__()
        self.project = os.environ.get("HERMES_CODER_PROJECT", "").strip()
        if self.project not in _PROJECTS:
            raise RuntimeError("HERMES_CODER_PROJECT должен быть velvet или max")
        self._launcher = SandboxLauncherClient()
        self._launcher.ping()

    def capabilities(self) -> dict[str, Any]:
        payload = super().capabilities()
        routing = payload.get("routing")
        if not isinstance(routing, dict):
            routing = {}
        return {
            **payload,
            "execution_backend": "host-sandbox-launcher",
            "routing": {
                **routing,
                "sandbox": {
                    "boundary": "disposable-docker-container",
                    "nested_bwrap": False,
                    "launcher_socket": True,
                    "per_run_mounts": True,
                    "no_silent_local_fallback": True,
                },
            },
        }

    def _mutation_policy(self, run_id: str) -> str:
        value = str(self.store.read(run_id).get("mutation_policy") or "read_only")
        if value not in {"read_only", "workspace_write"}:
            return "read_only"
        return value

    def _launch(
        self,
        *,
        run_id: str,
        model: str,
        prompt: str,
        route: str,
    ) -> dict[str, Any]:
        try:
            return self._launcher.run(
                run_id=run_id,
                project=self.project,
                workspace=Path(self.workspace),
                model=model,
                route=route,
                mutation_policy=self._mutation_policy(run_id),
                timeout_seconds=self.timeout_seconds,
                prompt=sandbox_visible_prompt(prompt, Path(self.workspace)),
            )
        except LauncherClientError as error:
            return {
                "returncode": 69,
                "stdout": "",
                "stderr": f"Sandbox launcher failed closed: {error}",
                "cancelled": bool(self.store.read(run_id).get("stop_requested")),
                "execution_started": False,
            }

    @staticmethod
    def _started(result: dict[str, Any]) -> bool:
        return bool(result.get("execution_started")) or primary_execution_started(
            str(result.get("stdout", ""))
        )

    def _run_once(self, run_id: str, model: str, prompt: str) -> dict[str, Any]:
        result = self._launch(
            run_id=run_id,
            model=model,
            prompt=prompt,
            route=self.primary_route,
        )
        if int(result.get("returncode", 1)) != 0 and self._started(result):
            self._primary_output_started = True
            self.store.update(
                run_id,
                primary_output_started=True,
                last_event={
                    "type": "primary_execution_started",
                    "model": model,
                    "automatic_retry": False,
                },
            )
            return {
                **result,
                "stdout": "",
                "stderr": (
                    "Primary Codex emitted tool execution events; automatic model "
                    "and provider fallback are blocked."
                ),
                "execution_started": True,
            }
        return result

    def _provider_run(
        self,
        run_id: str,
        prompt: str,
        model: str,
    ) -> dict[str, Any]:
        if self._primary_output_started or self._provider_output_started:
            return {
                "returncode": 78,
                "stdout": "",
                "stderr": "Provider fallback blocked after execution events.",
                "cancelled": False,
                "execution_started": True,
            }
        result = self._launch(
            run_id=run_id,
            model=model,
            prompt=prompt,
            route=self.provider_route,
        )
        if int(result.get("returncode", 1)) != 0 and self._started(result):
            self._provider_output_started = True
            self.store.update(
                run_id,
                provider_output_started=True,
                last_event={
                    "type": "provider_execution_started",
                    "model": model,
                    "automatic_retry": False,
                },
            )
            return {
                **result,
                "stdout": "",
                "stderr": (
                    "Provider emitted tool execution events; automatic provider "
                    "model retry is blocked."
                ),
                "execution_started": True,
            }
        return result

    def stop(self, run_id: str) -> dict[str, Any]:
        record = super().stop(run_id)
        if str(record.get("status")) not in _TERMINAL:
            try:
                self._launcher.cancel(run_id)
            except LauncherClientError:
                # stop_requested remains authoritative. No local execution fallback.
                pass
        return self.store.read(run_id)


def build_manager() -> AuditedTierProviderManager:
    backend = os.environ.get("CODEX_EXECUTION_BACKEND", "launcher").strip()
    if backend == "launcher":
        return LauncherTierProviderManager()
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
        f"Velvet launcher-backed tier runner listening on {host}:{port}; "
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
