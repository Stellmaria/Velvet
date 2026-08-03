#!/usr/bin/env python3
from __future__ import annotations

import os
from typing import Any

from codex_first_runner import (
    CodexFirstManager,
    Handler,
    ThreadingHTTPServer,
)


class SafeCodexFirstManager(CodexFirstManager):
    """Fail closed when a primary Codex process emitted execution events."""

    def __init__(self) -> None:
        super().__init__()
        self._run_baseline: str | None = None
        self._primary_output_started = False

    def _execute(
        self,
        run_id: str,
        prompt: str,
        instructions: str,
        selected_model: str,
    ) -> None:
        self._run_baseline = None
        self._primary_output_started = False
        super()._execute(run_id, prompt, instructions, selected_model)

    def _fingerprint(self) -> str:
        value = super()._fingerprint()
        if self._run_baseline is None:
            self._run_baseline = value
        return value

    def _run_once(self, run_id: str, model: str, prompt: str) -> dict[str, Any]:
        result = super()._run_once(run_id, model, prompt)
        if int(result.get("returncode", 1)) != 0 and str(result.get("stdout", "")).strip():
            self._primary_output_started = True
            self.store.update(
                run_id,
                primary_output_started=True,
                last_event={
                    "type": "primary_output_started",
                    "model": model,
                    "automatic_retry": False,
                },
            )
            return {
                **result,
                "stdout": "",
                "stderr": (
                    "Primary Codex emitted execution events; automatic model and "
                    "provider fallback are blocked."
                ),
            }
        return result

    def _provider_run(self, run_id: str, prompt: str) -> dict[str, Any]:
        if self._primary_output_started:
            return {
                "returncode": 78,
                "stdout": "",
                "stderr": "Provider fallback blocked after primary execution events.",
                "cancelled": False,
            }
        return super()._provider_run(run_id, prompt)

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
        super()._success(run_id, model, models, routes, route, reason, stdout)
        baseline = self._run_baseline
        if baseline is not None:
            self.store.update(
                run_id,
                mutation_started=super()._fingerprint() != baseline,
                primary_output_started=self._primary_output_started,
            )


def main() -> int:
    host = os.environ.get("CODEX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("CODEX_RUNNER_PORT", "8642"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("CODEX_RUNNER_PORT должен быть от 1024 до 65535")
    manager = SafeCodexFirstManager()
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet safe Codex-first runner listening on {host}:{port}; "
        f"default={manager.default_model}; provider_fallback={manager.provider_enabled}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
