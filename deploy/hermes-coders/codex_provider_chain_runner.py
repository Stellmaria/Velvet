#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass
from http import HTTPStatus
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
    TaskClassification,
    classify_task,
)
from codex_runner import RunnerError, redact_text, utc_now


@dataclass(frozen=True, slots=True)
class ProviderModel:
    model: str
    env_key: str
    credential_group: str


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    models: tuple[str, ...]
    degraded: bool
    review_required: bool


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
_ALLOWED_TASK_TYPES = frozenset(
    {"read_only", "docs", "code", "architecture", "security", "migration", "incident"}
)
_ALLOWED_TIERS = frozenset({"small", "standard", "complex", "high_risk"})
_ALLOWED_RISKS = frozenset({"low", "medium", "high", "critical"})
_ALLOWED_MUTATION_POLICIES = frozenset({"read_only", "workspace_pr"})
_PRIMARY_ROUTE_TEMPLATES = {
    "small": ("gpt-5.6-luna", "gpt-5.6-terra"),
    "standard": ("gpt-5.6-terra",),
    "complex": ("gpt-5.6-sol", "gpt-5.6-terra"),
    "high_risk": ("gpt-5.6-sol", "gpt-5.6-terra"),
}


def parse_provider_models(
    plural: str | None,
    singular: str | None,
) -> tuple[str, ...]:
    """Parse the provider catalog; route order is tier-specific elsewhere."""

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


def primary_route_for(
    requested_tier: str,
    allowed_models: tuple[str, ...],
) -> tuple[str, ...]:
    template = _PRIMARY_ROUTE_TEMPLATES[requested_tier]
    return tuple(model for model in template if model in allowed_models)


def provider_route_for(
    classification: TaskClassification,
    configured_models: tuple[str, ...],
) -> ProviderRoute:
    if classification.requested_tier == "small":
        template = (
            ("gpt-5.4-mini", "gpt-5.6-terra")
            if classification.task_type == "code"
            else ("gpt-5.6-luna", "gpt-5.6-terra")
        )
        degraded = False
        review_required = False
    elif classification.requested_tier == "standard":
        template = ("gpt-5.6-terra",)
        degraded = False
        review_required = False
    else:
        # Byesu Sol is not available to the production token groups. Terra may
        # still prepare code/tests/PR in the isolated workspace, never live prod.
        template = ("gpt-5.6-terra",)
        degraded = True
        review_required = True
    return ProviderRoute(
        models=tuple(model for model in template if model in configured_models),
        degraded=degraded,
        review_required=review_required,
    )


def _classification_from_record(record: dict[str, Any]) -> TaskClassification:
    task_type = str(record.get("task_type") or "")
    requested_tier = str(record.get("requested_tier") or "")
    risk = str(record.get("risk") or "")
    mutation_policy = str(record.get("mutation_policy") or "")
    model = str(record.get("selected_primary_model") or record.get("model") or "")
    if task_type not in _ALLOWED_TASK_TYPES:
        raise RuntimeError("Run ledger не содержит корректный task_type")
    if requested_tier not in _ALLOWED_TIERS:
        raise RuntimeError("Run ledger не содержит корректный requested_tier")
    if risk not in _ALLOWED_RISKS:
        raise RuntimeError("Run ledger не содержит корректный risk")
    if mutation_policy not in _ALLOWED_MUTATION_POLICIES:
        raise RuntimeError("Run ledger не содержит корректный mutation_policy")
    return TaskClassification(
        task_type=task_type,
        requested_tier=requested_tier,
        risk=risk,
        mutation_policy=mutation_policy,
        model=model,
    )


class ProviderChainManager(SafeCodexFirstManager):
    """Tier-aware Codex subscription first, then fail-closed Byesu routes."""

    def __init__(self) -> None:
        # Do not call CodexFirstManager.__init__: provider models use a separate
        # catalog from the Codex subscription allowlist.
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

        def route_payload(task_type: str, tier: str) -> dict[str, Any]:
            classification = TaskClassification(
                task_type=task_type,
                requested_tier=tier,
                risk={
                    "small": "low",
                    "standard": "medium",
                    "complex": "high",
                    "high_risk": "critical",
                }[tier],
                mutation_policy="workspace_pr",
                model=primary_route_for(tier, self.allowed_models)[0],
            )
            route = provider_route_for(classification, self.provider_models)
            return {
                "models": list(route.models),
                "degraded": route.degraded,
                "review_required": route.review_required,
            }

        return {
            **payload,
            "routing": {
                **routing,
                "primary_route": self.primary_route,
                "primary_routes_by_tier": {
                    tier: list(primary_route_for(tier, self.allowed_models))
                    for tier in ("small", "standard", "complex", "high_risk")
                },
                "provider_fallback": {
                    "enabled": self.provider_enabled,
                    "route": self.provider_route,
                    "models": list(self.provider_models),
                    "credential_groups": groups,
                    "routes_by_tier": {
                        "small_general": route_payload("read_only", "small"),
                        "small_code": route_payload("code", "small"),
                        "standard": route_payload("code", "standard"),
                        "complex": route_payload("architecture", "complex"),
                        "high_risk": route_payload("security", "high_risk"),
                    },
                    "after_mutation": False,
                    "after_tool_execution": False,
                    "downgrade_allowed": False,
                    "live_production_mutation": False,
                    "cooldown_seconds": self.cooldown_seconds,
                },
            },
        }

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {
            "input",
            "session_id",
            "instructions",
            "model",
            "task_type",
            "requested_tier",
            "tier",
            "risk",
            "mutation_policy",
        }
        if not set(payload).issubset(allowed_fields) or "input" not in payload:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Некорректный Runs API payload")
        if "tier" in payload and "requested_tier" in payload:
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "Передайте только requested_tier, без дублирующего tier",
            )
        prompt = payload.get("input")
        instructions = payload.get("instructions", "")
        session_id = payload.get("session_id")
        if not isinstance(prompt, str) or not prompt.strip():
            raise RunnerError(HTTPStatus.BAD_REQUEST, "input должен быть непустой строкой")
        if len(prompt) > 30_000:
            raise RunnerError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "input превышает 30000 символов",
            )
        if not isinstance(instructions, str) or len(instructions) > 8_000:
            raise RunnerError(
                HTTPStatus.BAD_REQUEST, "instructions имеет неверный формат"
            )
        if session_id is not None and (
            not isinstance(session_id, str) or len(session_id) > 200
        ):
            raise RunnerError(
                HTTPStatus.BAD_REQUEST, "session_id имеет неверный формат"
            )

        try:
            classification = classify_task(
                prompt,
                default=self.default_model,
                allowed=self.allowed_models,
                model=payload.get("model")
                if isinstance(payload.get("model"), str)
                else None,
                task_type=payload.get("task_type")
                if isinstance(payload.get("task_type"), str)
                else None,
                requested_tier=(
                    payload.get("requested_tier")
                    if isinstance(payload.get("requested_tier"), str)
                    else payload.get("tier")
                    if isinstance(payload.get("tier"), str)
                    else None
                ),
                risk=payload.get("risk")
                if isinstance(payload.get("risk"), str)
                else None,
                mutation_policy=payload.get("mutation_policy")
                if isinstance(payload.get("mutation_policy"), str)
                else None,
            )
        except ValueError as error:
            raise RunnerError(HTTPStatus.BAD_REQUEST, str(error)) from error

        if not self.workspace.is_dir() or not (self.workspace / ".git").exists():
            raise RunnerError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "CODEX_WORKSPACE не является Git checkout",
            )
        if not (self.codex_home / "auth.json").is_file():
            raise RunnerError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Codex не авторизован; выполните codex login --device-auth",
            )

        primary_models = primary_route_for(
            classification.requested_tier, self.allowed_models
        )
        if not primary_models:
            raise RunnerError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Для requested_tier нет primary Codex route",
            )
        provider_route = provider_route_for(
            classification, self.provider_models
        )
        if self.provider_enabled and not provider_route.models:
            raise RunnerError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Для requested_tier нет Byesu provider route",
            )

        run_id = uuid.uuid4().hex
        now = utc_now()
        record = {
            "run_id": run_id,
            "session_id": session_id,
            "status": "queued",
            "model": classification.model,
            "task_type": classification.task_type,
            "requested_tier": classification.requested_tier,
            "risk": classification.risk,
            "mutation_policy": classification.mutation_policy,
            "selected_primary_model": classification.model,
            "selected_primary_route": list(primary_models),
            "selected_provider_route": list(provider_route.models),
            "provider_degraded": provider_route.degraded,
            "review_required": provider_route.review_required,
            "live_production_mutation": False,
            "attempted_models": [],
            "attempted_routes": [],
            "created_at": now,
            "updated_at": now,
            "last_event": {
                "type": "queued",
                "model": classification.model,
                "requested_tier": classification.requested_tier,
            },
        }
        self.store.write(record)
        thread = threading.Thread(
            target=self._execute,
            args=(
                run_id,
                prompt.strip(),
                instructions.strip(),
                classification.model,
            ),
            name=f"codex-run-{run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return record

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
        record = self.store.read(run_id)
        if (
            record.get("status") == "completed"
            and record.get("mutation_policy") == "read_only"
            and record.get("mutation_started")
        ):
            self.store.update(
                run_id,
                status="failed",
                error="Read-only task changed the workspace; result rejected.",
                review_required=True,
                last_event={
                    "type": "read_only_mutation_rejected",
                    "automatic_retry": False,
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
            classification = _classification_from_record(record)
            if record.get("stop_requested"):
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
                primary_output_started=False,
                provider_output_started=False,
            )

            primary_models = primary_route_for(
                classification.requested_tier, self.allowed_models
            )
            if self._cooling_down():
                reason = "subscription_cooldown"
                errors.append("Codex subscription route is in cooldown")
            else:
                for model in primary_models:
                    models.append(model)
                    routes.append(f"{self.primary_route}:{model}")
                    degraded = (
                        classification.requested_tier in {"complex", "high_risk"}
                        and model != "gpt-5.6-sol"
                    )
                    self.store.update(
                        run_id,
                        model=model,
                        attempted_models=models,
                        attempted_routes=routes,
                        actual_route=self.primary_route,
                        degraded_execution=degraded,
                        review_required=bool(record.get("review_required")) or degraded,
                        last_event={
                            "type": "model_started",
                            "model": model,
                            "requested_tier": classification.requested_tier,
                            "degraded": degraded,
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
                        primary_output_started=execution_started,
                        fallback_reason=candidate,
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
                if reason is None:
                    reason = provider_fallback_reason("\n".join(errors))

            mutated = self._fingerprint() != baseline
            self.store.update(
                run_id,
                mutation_started=mutated,
                primary_output_started=self._primary_output_started,
                fallback_reason=reason,
            )
            if not (
                self.provider_enabled
                and reason
                and not mutated
                and not self._primary_output_started
            ):
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
                        "type": (
                            "provider_fallback_blocked"
                            if reason and (mutated or self._primary_output_started)
                            else "failed"
                        ),
                        "reason": reason,
                        "mutation_started": mutated,
                        "execution_started": self._primary_output_started,
                    },
                )
                return

            provider_route = provider_route_for(
                classification, self.provider_models
            )
            failed_groups: set[str] = set()
            for model in provider_route.models:
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
                    selected_provider_route=list(provider_route.models),
                    provider_degraded=provider_route.degraded,
                    degraded_execution=provider_route.degraded,
                    review_required=provider_route.review_required,
                    last_event={
                        "type": "provider_fallback_started",
                        "reason": reason,
                        "model": model,
                        "credential_group": spec.credential_group,
                        "requested_tier": classification.requested_tier,
                        "degraded": provider_route.degraded,
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
                mutated = self._fingerprint() != baseline
                execution_started = bool(result.get("execution_started"))
                self.store.update(
                    run_id,
                    mutation_started=mutated,
                    provider_output_started=self._provider_output_started,
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

            mutated = self._fingerprint() != baseline
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
                    "review_required": provider_route.review_required,
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
        f"Velvet tier-aware provider runner listening on {host}:{port}; "
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
