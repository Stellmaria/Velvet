#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_first_runner import (
    Handler,
    ThreadingHTTPServer,
    env_bool,
    provider_fallback_reason,
)
from codex_first_safe_runner import SafeCodexFirstManager, primary_execution_started
from codex_routed_runner import (
    RoutedCodexManager,
    primary_model_order,
    provider_route_for,
)
from codex_runner import redact_text, utc_now


@dataclass(frozen=True, slots=True)
class ProviderModel:
    model: str
    env_key: str
    credential_group: str


_PROVIDER_CATALOG: dict[str, ProviderModel] = {
    "gpt-5.4-mini": ProviderModel(
        "gpt-5.4-mini", "BYESU_HERMES_CODEX_API_KEY", "byesu-coder"
    ),
    "gpt-5.6-terra": ProviderModel(
        "gpt-5.6-terra", "BYESU_HERMES_CODEX_API_KEY", "byesu-coder"
    ),
    "gpt-5.6-luna": ProviderModel(
        "gpt-5.6-luna", "BYESU_HERMES_CODEX_API_KEY", "byesu-coder"
    ),
}
_DEFAULT_PROVIDER_MODELS = (
    "gpt-5.4-mini",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
)
_KEY_SCOPED_FAILURES = frozenset({"subscription_limit", "subscription_auth"})
_MODEL_ACCESS_FAILURE = re.compile(
    r"(?i)(model.{0,60}(?:not found|disabled|not entitled|permission denied|"
    r"access denied|does not exist)|unknown model|unsupported model)"
)


def parse_provider_models(
    plural: str | None,
    singular: str | None,
) -> tuple[str, ...]:
    """Parse the configured provider catalog, never a global retry chain."""

    raw = (plural or "").strip()
    if raw:
        models = [item.strip() for item in raw.split(",")]
        if any(not item for item in models):
            raise RuntimeError("CODEX_PROVIDER_FALLBACK_MODELS содержит пустую модель")
    else:
        legacy = (singular or "").strip()
        models = [legacy] if legacy else list(_DEFAULT_PROVIDER_MODELS)
    if len(models) != len(set(models)):
        raise RuntimeError("Provider fallback models не должны повторяться")
    unknown = [model for model in models if model not in _PROVIDER_CATALOG]
    if unknown:
        raise RuntimeError(
            "Некорректные provider fallback models: " + ", ".join(unknown)
        )
    return tuple(models)


def provider_failure_reason(output: str) -> str | None:
    if _MODEL_ACCESS_FAILURE.search(output):
        return "model_access_denied"
    return provider_fallback_reason(output)


class ProviderChainManager(SafeCodexFirstManager):
    """Tier-aware Codex first, then a fail-closed Byesu route."""

    def __init__(self) -> None:
        # The single-provider parent cannot represent a tier route catalog.
        RoutedCodexManager.__init__(self)
        self._execution_lock = threading.RLock()
        self.primary_route = "codex_subscription"
        self.provider_route = "byesu_provider"
        self.provider_enabled = env_bool("CODEX_PROVIDER_FALLBACK_ENABLED")
        self.provider_models = parse_provider_models(
            os.environ.get("CODEX_PROVIDER_FALLBACK_MODELS"),
            os.environ.get("CODEX_PROVIDER_FALLBACK_MODEL"),
        )
        self.provider_model = self.provider_models[0]
        self.provider_home: Path | None = None
        self.cooldown_seconds = max(
            60, int(os.environ.get("CODEX_PRIMARY_COOLDOWN_SECONDS", "1800"))
        )
        self._unavailable_until = 0.0
        self._route_lock = threading.RLock()
        self._run_baseline: str | None = None
        self._primary_output_started = False
        self._provider_output_started = False
        self.provider_homes: dict[str, Path] = {}
        if self.provider_enabled:
            missing = sorted(
                {
                    _PROVIDER_CATALOG[model].env_key
                    for model in self.provider_models
                    if not os.environ.get(_PROVIDER_CATALOG[model].env_key, "").strip()
                }
            )
            if missing:
                raise RuntimeError(
                    "Provider fallback включён без обязательных credentials: "
                    + ", ".join(missing)
                )
            self.provider_homes = {
                model: self._prepare_provider_home(_PROVIDER_CATALOG[model])
                for model in self.provider_models
            }

    def capabilities(self) -> dict[str, Any]:
        payload = RoutedCodexManager.capabilities(self)
        routing = payload.get("routing")
        if not isinstance(routing, dict):
            routing = {}
        groups: list[dict[str, Any]] = []
        seen: set[str] = set()
        for model in self.provider_models:
            group = _PROVIDER_CATALOG[model].credential_group
            if group in seen:
                continue
            seen.add(group)
            groups.append(
                {
                    "name": group,
                    "models": [
                        candidate
                        for candidate in self.provider_models
                        if _PROVIDER_CATALOG[candidate].credential_group == group
                    ],
                }
            )
        return {
            **payload,
            "routing": {
                **routing,
                "primary_route": self.primary_route,
                "provider_fallback": {
                    "enabled": self.provider_enabled,
                    "route": self.provider_route,
                    "catalog": list(self.provider_models),
                    "routes_by_tier": {
                        "small_general": list(provider_route_for("small", "general")),
                        "small_code": list(provider_route_for("small", "code")),
                        "standard": list(provider_route_for("standard", "code")),
                        "complex": list(provider_route_for("complex", "code")),
                        "high_risk": list(provider_route_for("high_risk", "code")),
                    },
                    "credential_groups": groups,
                    "after_mutation": False,
                    "after_execution_event": False,
                    "model_access_failure": "fail_closed",
                    "cooldown_seconds": self.cooldown_seconds,
                },
            },
        }

    def _prepare_provider_home(self, spec: ProviderModel) -> Path:
        root = Path(
            tempfile.mkdtemp(prefix=f"codex-provider-{spec.model}-", dir="/tmp")
        ).resolve()
        os.chmod(root, 0o700)
        for name in ("AGENTS.md", "output.schema.json"):
            source = self.codex_home / name
            if not source.is_file():
                raise RuntimeError(f"CODEX_HOME не содержит {name}")
            shutil.copyfile(source, root / name)
            os.chmod(root / name, 0o600)
        config = f'''model = "{spec.model}"
model_provider = "byesu"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
approval_policy = "never"
check_for_update_on_startup = false

[model_providers.byesu]
name = "Byesu"
base_url = "https://byesu.com/v1"
env_key = "{spec.env_key}"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 2
stream_max_retries = 2
stream_idle_timeout_ms = 300000

[sandbox_workspace_write]
network_access = true

[shell_environment_policy]
ignore_default_excludes = true
exclude = [
  "API_SERVER_KEY",
  "BYESU_HERMES_CODEX_API_KEY",
  "CODEX_RUNNER_API_KEY",
  "DATABASE_URL",
  "PGPASSWORD",
  "TELEGRAM_BOT_TOKEN",
]

[features]
apps = false
plugins = false
tool_suggest = false
'''
        (root / "config.toml").write_text(config, encoding="utf-8")
        os.chmod(root / "config.toml", 0o600)
        return root

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
        home = self.provider_homes.get(model)
        if home is None:
            raise RuntimeError(f"Provider home не подготовлен для {model}")
        process = subprocess.Popen(
            [
                self.codex_bin,
                "exec",
                "--json",
                "--model",
                model,
                "--sandbox",
                "workspace-write",
                "--output-schema",
                str(home / "output.schema.json"),
                "-",
            ],
            cwd=self.workspace,
            env={**os.environ, "CODEX_HOME": str(home)},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        with self._process_lock:
            self._processes[run_id] = process
        try:
            try:
                stdout, stderr = process.communicate(
                    input=prompt, timeout=self.timeout_seconds
                )
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    stdout, stderr = process.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout, stderr = process.communicate()
                stderr = (stderr or "") + "\nProvider fallback timed out"
        finally:
            with self._process_lock:
                self._processes.pop(run_id, None)
        result = {
            "returncode": process.returncode if process.returncode is not None else 1,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "cancelled": bool(self.store.read(run_id).get("stop_requested")),
            "execution_started": False,
        }
        if int(result["returncode"]) != 0 and primary_execution_started(
            str(result["stdout"])
        ):
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
            result.update(
                stdout="",
                stderr=(
                    "Provider emitted tool execution events; automatic provider "
                    "model retry is blocked."
                ),
                execution_started=True,
            )
        return result

    def _finish_failed(
        self,
        run_id: str,
        *,
        models: list[str],
        routes: list[str],
        errors: list[str],
        reason: str | None,
        baseline: str,
        event_type: str,
        actual_route: str | None,
    ) -> None:
        mutated = self._fingerprint() != baseline
        self.store.update(
            run_id,
            status="failed",
            finished_at=utc_now(),
            attempted_models=models,
            attempted_routes=routes,
            actual_route=actual_route,
            fallback_reason=reason,
            mutation_started=mutated,
            error="\n".join(errors)[-12_000:],
            last_event={
                "type": event_type,
                "reason": reason,
                "mutation_started": mutated,
                "execution_started": (
                    self._primary_output_started or self._provider_output_started
                ),
            },
        )

    def _execute(
        self,
        run_id: str,
        prompt: str,
        instructions: str,
        selected_model: str,
    ) -> None:
        with self._execution_lock:
            self._run_baseline = None
            self._primary_output_started = False
            self._provider_output_started = False
            record = self.store.read(run_id)
            if record.get("stop_requested"):
                self.store.update(
                    run_id,
                    status="cancelled",
                    finished_at=utc_now(),
                    requested_route=self.primary_route,
                    attempted_routes=[],
                )
                return

            requested_tier = str(record.get("requested_tier") or "standard")
            task_type = str(record.get("task_type") or "code")
            baseline = self._fingerprint()
            combined = prompt if not instructions else f"{instructions}\n\n{prompt}"
            models: list[str] = []
            routes: list[str] = []
            errors: list[str] = []
            reason: str | None = None
            self.store.update(
                run_id,
                status="running",
                started_at=utc_now(),
                requested_route=self.primary_route,
                actual_route=None,
                attempted_routes=[],
                fallback_reason=None,
                mutation_started=False,
            )

            if self._cooling_down():
                reason = "subscription_cooldown"
                errors.append("Codex subscription route is in cooldown")
            else:
                primary_models = tuple(
                    model
                    for model in primary_model_order(selected_model, requested_tier)
                    if model in self.allowed_models
                )
                for model in primary_models:
                    models.append(model)
                    routes.append(f"{self.primary_route}:{model}")
                    self.store.update(
                        run_id,
                        model=model,
                        attempted_models=models,
                        attempted_routes=routes,
                        actual_route=self.primary_route,
                        last_event={
                            "type": "model_started",
                            "model": model,
                            "requested_tier": requested_tier,
                        },
                    )
                    result = self._run_once(run_id, model, combined)
                    if result["cancelled"]:
                        self.store.update(
                            run_id,
                            status="cancelled",
                            finished_at=utc_now(),
                            attempted_models=models,
                            attempted_routes=routes,
                            actual_route=self.primary_route,
                        )
                        return
                    if int(result["returncode"]) == 0:
                        self._success(
                            run_id,
                            model,
                            models,
                            routes,
                            self.primary_route,
                            None,
                            str(result["stdout"]),
                        )
                        return

                    raw = f"{result['stdout']}\n{result['stderr']}"
                    details = redact_text(
                        str(result["stderr"] or result["stdout"]).strip()[-4000:]
                    )
                    errors.append(f"{self.primary_route}/{model}: {details}")
                    candidate = provider_fallback_reason(raw)
                    mutated = self._fingerprint() != baseline
                    execution_started = self._primary_output_started
                    self.store.update(
                        run_id,
                        mutation_started=mutated,
                        fallback_reason=candidate,
                        last_event={
                            "type": "primary_model_failed",
                            "model": model,
                            "reason": candidate,
                            "mutation_started": mutated,
                            "execution_started": execution_started,
                        },
                    )
                    if mutated or execution_started:
                        reason = candidate
                        break
                    if candidate in _KEY_SCOPED_FAILURES:
                        reason = candidate
                        self._open_cooldown()
                        break
                    if candidate == "codex_capacity":
                        reason = candidate
                        continue
                    reason = candidate
                    break

            mutated = self._fingerprint() != baseline
            if (
                not self.provider_enabled
                or not reason
                or mutated
                or self._primary_output_started
            ):
                self._finish_failed(
                    run_id,
                    models=models,
                    routes=routes,
                    errors=errors,
                    reason=reason,
                    baseline=baseline,
                    event_type=(
                        "provider_fallback_blocked"
                        if reason and (mutated or self._primary_output_started)
                        else "failed"
                    ),
                    actual_route=(self.primary_route if routes else None),
                )
                return

            requested_route = provider_route_for(requested_tier, task_type)
            if not requested_route or requested_route[0] not in self.provider_models:
                errors.append(
                    "Required provider route is unavailable; fail closed before model downgrade"
                )
                self._finish_failed(
                    run_id,
                    models=models,
                    routes=routes,
                    errors=errors,
                    reason="provider_route_unavailable",
                    baseline=baseline,
                    event_type="provider_route_unavailable",
                    actual_route=self.primary_route,
                )
                return
            route_models = tuple(
                model for model in requested_route if model in self.provider_models
            )
            if requested_tier in {"complex", "high_risk"}:
                combined = (
                    "DEGRADED COMPLEX ROUTE: work only in the isolated workspace; "
                    "prepare code, tests and one PR; never merge, deploy, restart, "
                    "rollback, read production .env, use Docker socket or systemd. "
                    "Independent review is mandatory.\n\n" + combined
                )
                self.store.update(
                    run_id,
                    review_required=True,
                    degraded_provider_route=True,
                )

            failed_groups: set[str] = set()
            for model in route_models:
                spec = _PROVIDER_CATALOG[model]
                if spec.credential_group in failed_groups:
                    continue
                models.append(model)
                routes.append(f"{self.provider_route}:{model}")
                self.store.update(
                    run_id,
                    status="running",
                    model=model,
                    attempted_models=models,
                    attempted_routes=routes,
                    actual_route=self.provider_route,
                    last_event={
                        "type": "provider_fallback_started",
                        "reason": reason,
                        "model": model,
                        "credential_group": spec.credential_group,
                        "requested_tier": requested_tier,
                    },
                )
                result = self._provider_run(run_id, combined, model)
                if result["cancelled"]:
                    self.store.update(
                        run_id,
                        status="cancelled",
                        finished_at=utc_now(),
                        attempted_models=models,
                        attempted_routes=routes,
                        actual_route=self.provider_route,
                    )
                    return
                if int(result["returncode"]) == 0:
                    self._success(
                        run_id,
                        model,
                        models,
                        routes,
                        self.provider_route,
                        str(reason),
                        str(result["stdout"]),
                    )
                    return

                raw = f"{result['stdout']}\n{result['stderr']}"
                details = redact_text(
                    str(result["stderr"] or result["stdout"]).strip()[-4000:]
                )
                errors.append(f"{self.provider_route}/{model}: {details}")
                retry_reason = provider_failure_reason(raw)
                mutated = self._fingerprint() != baseline
                execution_started = bool(result.get("execution_started"))
                self.store.update(
                    run_id,
                    mutation_started=mutated,
                    last_event={
                        "type": "provider_model_failed",
                        "model": model,
                        "reason": retry_reason,
                        "mutation_started": mutated,
                        "execution_started": execution_started,
                    },
                )
                if mutated or execution_started:
                    break
                if retry_reason in _KEY_SCOPED_FAILURES:
                    failed_groups.add(spec.credential_group)
                    continue
                if retry_reason == "codex_capacity":
                    continue
                # Permanent model access/entitlement errors fail closed. This keeps
                # an unverified Mini from silently becoming a Terra run.
                break

            self._finish_failed(
                run_id,
                models=models,
                routes=routes,
                errors=errors,
                reason=reason,
                baseline=baseline,
                event_type="provider_fallback_failed",
                actual_route=self.provider_route,
            )


def main() -> int:
    host = os.environ.get("CODEX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("CODEX_RUNNER_PORT", "8642"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("CODEX_RUNNER_PORT должен быть от 1024 до 65535")
    manager = ProviderChainManager()
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet tier-aware provider runner listening on {host}:{port}; "
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
