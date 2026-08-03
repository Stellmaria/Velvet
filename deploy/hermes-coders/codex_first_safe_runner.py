#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from typing import Any

from codex_first_runner import (
    CodexFirstManager,
    Handler,
    ThreadingHTTPServer,
)

_EXECUTION_ITEM_TYPES = frozenset(
    {
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "collab_tool_call",
        "dynamic_tool_call",
    }
)


def primary_execution_started(stdout: str) -> bool:
    """Return true only after Codex emitted an actual tool/file execution item.

    Lifecycle events such as thread.started and turn.started are intentionally
    ignored so a quota/auth failure before tool execution can still use the
    bounded provider fallback.
    """

    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().casefold()
        if item_type in _EXECUTION_ITEM_TYPES:
            return True
        if item_type.endswith("_tool_call") or item_type.endswith("_execution"):
            return True
    return False


class SafeCodexFirstManager(CodexFirstManager):
    """Fail closed after primary Codex tool execution, not lifecycle output."""

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
        stdout = str(result.get("stdout", ""))
        if int(result.get("returncode", 1)) != 0 and primary_execution_started(stdout):
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
