#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_first_runner import (
    CodexFirstManager,
    Handler,
    ThreadingHTTPServer,
    env_bool,
    provider_fallback_reason,
)
from codex_first_safe_runner import SafeCodexFirstManager, primary_execution_started
from codex_routed_runner import RoutedCodexManager
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
        "gpt-5.6-luna", "BYESU_HERMES_GPT_PRO_API_KEY", "byesu-gpt-pro"
    ),
}
_DEFAULT_PROVIDER_MODELS = (
    "gpt-5.4-mini",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
)
_KEY_SCOPED_FAILURES = frozenset({"subscription_limit", "subscription_auth"})


def parse_provider_models(
    plural: str | None,
    singular: str | None,
) -> tuple[str, ...]:
    """Parse the Byesu chain independently from the Codex model allowlist."""

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


class ProviderChainManager(SafeCodexFirstManager):
    """Codex subscription first, then a fail-closed multi-model Byesu chain."""

    def __init__(self) -> None:
        # Do not call CodexFirstManager.__init__: its provider model is restricted
        # by the Codex Luna/Terra/Sol allowlist and it prepares only one home.
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
                    "model": self.provider_model,
                    "models": list(self.provider_models),
                    "credential_groups": groups,
                    "after_mutation": False,
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
  "BYESU_HERMES_GPT_PRO_API_KEY",
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
        if int(result["returncode"]) != 0 and primary_execution_started(result["stdout"]):
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
            enabled = self.provider_enabled
            self.provider_enabled = False
            try:
                CodexFirstManager._execute(
                    self, run_id, prompt, instructions, selected_model
                )
            finally:
                self.provider_enabled = enabled

            record = self.store.read(run_id)
            if record.get("status") in {"completed", "cancelled"}:
                return
            reason = record.get("fallback_reason")
            baseline = self._run_baseline
            mutated = bool(record.get("mutation_started"))
            if baseline is not None:
                mutated = mutated or self._fingerprint() != baseline
            if not enabled or not reason or mutated or self._primary_output_started:
                return

            combined = prompt if not instructions else f"{instructions}\n\n{prompt}"
            models = list(record.get("attempted_models") or [])
            routes = list(record.get("attempted_routes") or [])
            errors = [str(record.get("error") or "").strip()]
            errors = [item for item in errors if item]
            failed_groups: set[str] = set()

            for model in self.provider_models:
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
                retry_reason = provider_fallback_reason(raw)
                mutated = baseline is not None and self._fingerprint() != baseline
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
                break

            mutated = baseline is not None and self._fingerprint() != baseline
            self.store.update(
                run_id,
                status="failed",
                finished_at=utc_now(),
                attempted_models=models,
                attempted_routes=routes,
                actual_route=self.provider_route,
                fallback_reason=reason,
                mutation_started=mutated,
                error="\n".join(errors)[-12000:],
                last_event={
                    "type": "provider_fallback_failed",
                    "mutation_started": mutated,
                },
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
        f"Velvet provider-chain runner listening on {host}:{port}; "
        f"default={manager.default_model}; provider_models={manager.provider_models}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
