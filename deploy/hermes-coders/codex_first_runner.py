#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from codex_runner import (
    Handler,
    ThreadingHTTPServer,
    _RETRYABLE_MODEL_ERRORS,
    fallback_order,
    parse_jsonl_output,
    parse_structured_output,
    redact_text,
    render_legacy_output,
    utc_now,
)
from codex_routed_runner import RoutedCodexManager

_TRUE = frozenset({"1", "true", "yes", "on"})
_LIMIT = re.compile(
    r"(?i)(usage.?limit|agentic.?limit|allowance|quota|"
    r"subscription.{0,40}(?:limit|exhaust|reached)|"
    r"credits?.{0,30}(?:required|exhaust|empty)|"
    r"rate.?limit|too many requests|(?:^|\D)429(?:\D|$))"
)
_AUTH = re.compile(
    r"(?i)(device.?auth|login.{0,30}(?:required|expired)|"
    r"auth(?:entication|orization)?.{0,40}(?:expired|invalid|failed|required)|"
    r"token.{0,30}(?:expired|invalid)|(?:^|\D)401(?:\D|$)|"
    r"(?:^|\D)403(?:\D|$))"
)
_CAPACITY = re.compile(
    r"(?i)(capacity|temporar(?:y|ily).?unavailable|service.?unavailable|"
    r"model.{0,40}(?:unavailable|not available|not found|disabled)|"
    r"(?:^|\D)50[234](?:\D|$))"
)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().casefold() in _TRUE


def provider_fallback_reason(output: str) -> str | None:
    if _LIMIT.search(output):
        return "subscription_limit"
    if _AUTH.search(output):
        return "subscription_auth"
    if _CAPACITY.search(output):
        return "codex_capacity"
    return None


class CodexFirstManager(RoutedCodexManager):
    """ChatGPT Codex first; Byesu only before any Git mutation."""

    def __init__(self) -> None:
        super().__init__()
        self.primary_route = "codex_subscription"
        self.provider_route = "byesu_provider"
        self.provider_enabled = env_bool("CODEX_PROVIDER_FALLBACK_ENABLED")
        self.provider_model = os.environ.get(
            "CODEX_PROVIDER_FALLBACK_MODEL", "gpt-5.6-terra"
        ).strip()
        self.cooldown_seconds = max(
            60, int(os.environ.get("CODEX_PRIMARY_COOLDOWN_SECONDS", "1800"))
        )
        self._unavailable_until = 0.0
        self._route_lock = threading.RLock()
        self.provider_home: Path | None = None
        if self.provider_model not in self.allowed_models:
            raise RuntimeError("Некорректная provider fallback model")
        if self.provider_enabled:
            if not os.environ.get("BYESU_HERMES_CODEX_API_KEY", "").strip():
                raise RuntimeError("Provider fallback включён без Byesu key")
            self.provider_home = self._prepare_provider_home()

    def capabilities(self) -> dict[str, Any]:
        payload = super().capabilities()
        routing = payload.get("routing")
        if not isinstance(routing, dict):
            routing = {}
        return {
            **payload,
            "routing": {
                **routing,
                "primary_route": self.primary_route,
                "provider_fallback": {
                    "enabled": self.provider_enabled,
                    "route": self.provider_route,
                    "model": self.provider_model,
                    "after_mutation": False,
                    "cooldown_seconds": self.cooldown_seconds,
                },
            },
        }

    def _prepare_provider_home(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="codex-provider-", dir="/tmp")).resolve()
        os.chmod(root, 0o700)
        for name in ("AGENTS.md", "output.schema.json"):
            source = self.codex_home / name
            if not source.is_file():
                raise RuntimeError(f"CODEX_HOME не содержит {name}")
            shutil.copyfile(source, root / name)
            os.chmod(root / name, 0o600)
        config = f'''model = "{self.provider_model}"
model_provider = "byesu"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
approval_policy = "never"
check_for_update_on_startup = false

[model_providers.byesu]
name = "Byesu"
base_url = "https://byesu.com/v1"
env_key = "BYESU_HERMES_CODEX_API_KEY"
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

    def _git(self, *args: str) -> bytes:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.workspace,
                check=False,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("Git fingerprint недоступен") from error
        if result.returncode:
            details = redact_text(
                (result.stderr or b"").decode("utf-8", errors="replace")[-1000:]
            )
            raise RuntimeError(f"Git fingerprint failed: {details or result.returncode}")
        return result.stdout

    def _fingerprint(self) -> str:
        chunks = (
            self._git("rev-parse", "HEAD"),
            self._git("rev-parse", "--abbrev-ref", "HEAD"),
            self._git(
                "for-each-ref",
                "--format=%(refname)%00%(objectname)%00",
                "refs/heads",
                "refs/tags",
            ),
            self._git("status", "--porcelain=v1", "-z", "--untracked-files=all"),
        )
        digest = hashlib.sha256()
        for chunk in chunks:
            digest.update(len(chunk).to_bytes(8, "big"))
            digest.update(chunk)
        return digest.hexdigest()

    def _cooling_down(self) -> bool:
        with self._route_lock:
            return time.monotonic() < self._unavailable_until

    def _open_cooldown(self) -> None:
        with self._route_lock:
            self._unavailable_until = time.monotonic() + self.cooldown_seconds

    def _provider_run(self, run_id: str, prompt: str) -> dict[str, Any]:
        if self.provider_home is None:
            raise RuntimeError("Provider home не подготовлен")
        command = [
            self.codex_bin,
            "exec",
            "--json",
            "--model",
            self.provider_model,
            "--sandbox",
            "workspace-write",
            "--output-schema",
            str(self.provider_home / "output.schema.json"),
            "-",
        ]
        process = subprocess.Popen(
            command,
            cwd=self.workspace,
            env={**os.environ, "CODEX_HOME": str(self.provider_home)},
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
            return {
                "returncode": process.returncode if process.returncode is not None else 1,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "cancelled": bool(self.store.read(run_id).get("stop_requested")),
            }
        finally:
            with self._process_lock:
                self._processes.pop(run_id, None)

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
        output, usage, last_event = parse_jsonl_output(stdout)
        try:
            structured = parse_structured_output(output)
        except ValueError as error:
            self.store.update(
                run_id,
                status="failed",
                finished_at=utc_now(),
                attempted_models=models,
                attempted_routes=routes,
                actual_route=route,
                fallback_reason=reason,
                error=str(error),
                last_event={"type": "invalid_structured_output", "route": route},
            )
            return
        self.store.update(
            run_id,
            status="completed",
            finished_at=utc_now(),
            model=model,
            attempted_models=models,
            attempted_routes=routes,
            actual_route=route,
            fallback_reason=reason,
            output=render_legacy_output(structured),
            structured_output=structured,
            usage=usage,
            last_event=last_event or {"type": "completed", "route": route},
        )

    def _execute(
        self,
        run_id: str,
        prompt: str,
        instructions: str,
        selected_model: str,
    ) -> None:
        with self._execution_lock:
            if self.store.read(run_id).get("stop_requested"):
                self.store.update(
                    run_id,
                    status="cancelled",
                    finished_at=utc_now(),
                    requested_route=self.primary_route,
                    attempted_routes=[],
                )
                return

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
                for model in fallback_order(selected_model, self.allowed_models):
                    models.append(model)
                    routes.append(f"{self.primary_route}:{model}")
                    self.store.update(
                        run_id,
                        model=model,
                        attempted_models=models,
                        attempted_routes=routes,
                        actual_route=self.primary_route,
                        last_event={"type": "model_started", "model": model},
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
                    self.store.update(
                        run_id,
                        mutation_started=mutated,
                        fallback_reason=candidate,
                    )
                    if mutated:
                        reason = candidate
                        break
                    if candidate in {"subscription_limit", "subscription_auth"}:
                        reason = candidate
                        self._open_cooldown()
                        break
                    if not _RETRYABLE_MODEL_ERRORS.search(raw):
                        break
                if reason is None:
                    reason = provider_fallback_reason("\n".join(errors))

            mutated = self._fingerprint() != baseline
            self.store.update(
                run_id, mutation_started=mutated, fallback_reason=reason
            )
            if not (self.provider_enabled and reason and not mutated):
                self.store.update(
                    run_id,
                    status="failed",
                    finished_at=utc_now(),
                    attempted_models=models,
                    attempted_routes=routes,
                    fallback_reason=reason,
                    mutation_started=mutated,
                    error="\n".join(errors)[-12000:],
                    last_event={
                        "type": "provider_fallback_blocked" if reason and mutated else "failed",
                        "reason": reason,
                        "mutation_started": mutated,
                    },
                )
                return

            models.append(self.provider_model)
            routes.append(f"{self.provider_route}:{self.provider_model}")
            self.store.update(
                run_id,
                model=self.provider_model,
                attempted_models=models,
                attempted_routes=routes,
                actual_route=self.provider_route,
                last_event={"type": "provider_fallback_started", "reason": reason},
            )
            result = self._provider_run(run_id, combined)
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
                    self.provider_model,
                    models,
                    routes,
                    self.provider_route,
                    reason,
                    str(result["stdout"]),
                )
                return

            mutated = self._fingerprint() != baseline
            details = redact_text(
                str(result["stderr"] or result["stdout"]).strip()[-4000:]
            )
            errors.append(f"{self.provider_route}/{self.provider_model}: {details}")
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
    manager = CodexFirstManager()
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet Codex-first runner listening on {host}:{port}; "
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
