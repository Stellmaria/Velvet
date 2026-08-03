#!/usr/bin/env python3
from __future__ import annotations

import os
import threading
from typing import Any

from codex_first_runner import Handler, ThreadingHTTPServer
from codex_provider_chain_runner import ProviderChainManager
from codex_runner import utc_now


class AuditedTierProviderManager(ProviderChainManager):
    """Record successful mutations and fail closed for read-only runs."""

    def __init__(self) -> None:
        super().__init__()
        self._baseline_lock = threading.RLock()
        self._run_baselines: dict[str, str] = {}

    def capabilities(self) -> dict[str, Any]:
        payload = super().capabilities()
        routing = payload.get("routing")
        if not isinstance(routing, dict):
            routing = {}
        return {
            **payload,
            "routing": {
                **routing,
                "mutation_audit": {
                    "successful_runs": True,
                    "read_only_fail_closed": True,
                },
            },
        }

    def _execute(
        self,
        run_id: str,
        prompt: str,
        instructions: str,
        selected_model: str,
    ) -> None:
        with self._baseline_lock:
            self._run_baselines[run_id] = self._fingerprint()
        try:
            super()._execute(run_id, prompt, instructions, selected_model)
        finally:
            with self._baseline_lock:
                self._run_baselines.pop(run_id, None)

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
        with self._baseline_lock:
            baseline = self._run_baselines.get(run_id)
        mutated = baseline is not None and self._fingerprint() != baseline
        record = self.store.read(run_id)
        mutation_policy = str(record.get("mutation_policy") or "workspace_write")
        self.store.update(run_id, mutation_started=mutated)
        if mutation_policy == "read_only" and mutated:
            self.store.update(
                run_id,
                status="failed",
                finished_at=utc_now(),
                model=model,
                attempted_models=models,
                attempted_routes=routes,
                actual_route=route,
                fallback_reason=reason,
                mutation_started=True,
                error="Read-only run mutated the isolated workspace; result rejected.",
                last_event={
                    "type": "read_only_mutation_blocked",
                    "model": model,
                    "route": route,
                    "mutation_started": True,
                },
            )
            return
        super()._success(run_id, model, models, routes, route, reason, stdout)


def main() -> int:
    host = os.environ.get("CODEX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("CODEX_RUNNER_PORT", "8642"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("CODEX_RUNNER_PORT должен быть от 1024 до 65535")
    manager = AuditedTierProviderManager()
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet audited tier-aware provider runner listening on {host}:{port}; "
        f"default={manager.default_model}; provider_catalog={manager.provider_models}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
