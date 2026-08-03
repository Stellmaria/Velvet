#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_TIERS = ("small", "standard", "complex", "high_risk")
_TASK_TYPES = ("general", "code", "read_only", "documentation", "incident")
_COMPLEXITIES = ("small", "standard", "complex")
_RISKS = ("low", "medium", "high", "critical")
_MUTATION_POLICIES = ("read_only", "workspace_write", "isolated_pr_only")
_SECRET = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+|"
    r"[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*[=:]\s*)"
    r"[^\s,;]+"
)


class DelegateError(RuntimeError):
    pass


def redact_text(value: str) -> str:
    return _SECRET.sub(r"\1[REDACTED]", value)


def _required_env(name: str, *, minimum: int = 1) -> str:
    value = os.environ.get(name, "").strip()
    if len(value) < minimum:
        raise DelegateError(f"{name} отсутствует или короче {minimum} символов")
    return value


def build_payload(
    task: str,
    *,
    project: str,
    model: str | None,
    task_type: str,
    complexity: str,
    risk: str,
    mutation_policy: str,
    requested_tier: str,
) -> dict[str, Any]:
    clean = task.strip()
    if not clean:
        raise DelegateError("Задача пуста")
    if len(clean) > 30_000:
        raise DelegateError("Задача превышает 30000 символов")
    payload: dict[str, Any] = {
        "input": clean,
        "session_id": f"telegram-{project}-{uuid.uuid4().hex}",
        "instructions": (
            f"Ты Codex-first coder проекта {project}. Сохрани requested tier, "
            "работай только в текущем repository и верни schema-bound JSON. "
            "Не merge, не deploy и не меняй production."
        ),
        "task_type": task_type,
        "complexity": complexity,
        "risk": risk,
        "mutation_policy": mutation_policy,
        "requested_tier": requested_tier,
    }
    if model:
        payload["model"] = model
    return payload


class RunnerClient:
    def __init__(self) -> None:
        self.base_url = _required_env("HERMES_CODEX_DELEGATE_URL").rstrip("/")
        self.token = _required_env("CODEX_RUNNER_API_KEY", minimum=24)
        self.project = _required_env("HERMES_CODEX_DELEGATE_PROJECT")
        self.timeout_seconds = max(
            30,
            int(os.environ.get("HERMES_CODEX_DELEGATE_TIMEOUT_SECONDS", "7200")),
        )
        self.poll_seconds = max(
            1.0,
            float(os.environ.get("HERMES_CODEX_DELEGATE_POLL_SECONDS", "3")),
        )

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[-2000:]
            raise DelegateError(
                f"Runner HTTP {error.code}: {redact_text(details)}"
            ) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise DelegateError(
                f"Runner недоступен: {type(error).__name__}"
            ) from error
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise DelegateError("Runner вернул повреждённый JSON") from error
        if not isinstance(result, dict):
            raise DelegateError("Runner вернул неожиданный тип ответа")
        return result

    def run(self, task: str, **routing: Any) -> dict[str, Any]:
        submitted = self.request(
            "POST",
            "/v1/runs",
            build_payload(task, project=self.project, **routing),
        )
        run_id = submitted.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise DelegateError("Runner не вернул run_id")
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            record = self.request("GET", f"/v1/runs/{run_id}")
            if record.get("status") in _TERMINAL:
                return record
            time.sleep(self.poll_seconds)
        raise DelegateError(
            f"Run {run_id} не завершился за {self.timeout_seconds} секунд"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delegate one tier-aware Telegram coder task"
    )
    parser.add_argument(
        "--model",
        choices=("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
    )
    parser.add_argument("--task-type", choices=_TASK_TYPES, required=True)
    parser.add_argument("--complexity", choices=_COMPLEXITIES, required=True)
    parser.add_argument("--risk", choices=_RISKS, required=True)
    parser.add_argument(
        "--mutation-policy", choices=_MUTATION_POLICIES, required=True
    )
    parser.add_argument("--tier", choices=_TIERS, required=True)
    return parser


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv[1:])
    task = sys.stdin.read()
    client = RunnerClient()
    result = client.run(
        task,
        model=args.model,
        task_type=args.task_type,
        complexity=args.complexity,
        risk=args.risk,
        mutation_policy=args.mutation_policy,
        requested_tier=args.tier,
    )
    public = {
        key: result.get(key)
        for key in (
            "run_id",
            "status",
            "task_type",
            "complexity",
            "risk",
            "mutation_policy",
            "requested_tier",
            "selected_primary_model",
            "selected_provider_route",
            "model",
            "requested_route",
            "actual_route",
            "attempted_models",
            "attempted_routes",
            "fallback_reason",
            "mutation_started",
            "review_required",
            "degraded_provider_route",
            "output",
            "structured_output",
            "error",
        )
        if key in result
    }
    print(json.dumps(public, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "completed" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except DelegateError as error:
        print(f"Codex delegation failed: {error}", file=sys.stderr)
        raise SystemExit(2)
