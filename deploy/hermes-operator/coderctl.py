#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
TIERS = ("small", "standard", "complex", "high_risk")
TASK_TYPES = ("general", "code", "read_only", "documentation", "incident")
COMPLEXITIES = ("small", "standard", "complex")
RISKS = ("low", "medium", "high", "critical")
MUTATION_POLICIES = ("read_only", "workspace_write", "isolated_pr_only")
_ROUTING_FIELDS = (
    "task_type",
    "complexity",
    "risk",
    "mutation_policy",
    "requested_tier",
    "selected_primary_model",
    "selected_provider_route",
    "attempted_models",
    "attempted_routes",
    "actual_route",
    "fallback_reason",
    "mutation_started",
    "review_required",
    "degraded_provider_route",
)
_PROJECTS = {
    "velvet": ("Stellmaria/Velvet", "@velvet_private_coder_bot"),
    "max": ("Stellmaria/romatic_club_bot_max", "@romatic_max_coder_bot"),
}
_SECRET_KEY = re.compile(r"(?i)(token|secret|password|api[_-]?key|authorization)")
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*"
        r"\s*[=:]\s*)[^\s,;]+"
    ),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
)


class CoderApiError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_text(value: str) -> str:
    result = value
    for pattern in _SECRET_TEXT_PATTERNS:
        if pattern.groups:
            result = pattern.sub(r"\1[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    def _load_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CoderApiError(f"Повреждён журнал задач: {error}") from error
        if not isinstance(payload, list):
            raise CoderApiError("Журнал задач должен содержать JSON-массив.")
        return [item for item in payload if isinstance(item, dict)]

    def _write_unlocked(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            dir=str(self.path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(records, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def list(self) -> list[dict[str, Any]]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            return self._load_unlocked()

    def upsert(self, record: dict[str, Any]) -> None:
        task_id = str(record.get("task_id", ""))
        if not task_id:
            raise CoderApiError("Запись журнала не содержит task_id.")
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            records = self._load_unlocked()
            for index, current in enumerate(records):
                if current.get("task_id") == task_id:
                    records[index] = {**current, **record}
                    break
            else:
                records.append(record)
            records.sort(
                key=lambda item: str(item.get("created_at", "")), reverse=True
            )
            self._write_unlocked(records)

    def find(self, reference: str) -> dict[str, Any] | None:
        for record in self.list():
            if record.get("task_id") == reference or record.get("run_id") == reference:
                return record
        return None


class RouterClient:
    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.base_url = os.getenv(
            "HERMES_CODER_ROUTER_BASE_URL",
            "http://hermes-coder-router:8878",
        ).strip().rstrip("/")
        self.token_file = Path(
            os.getenv(
                "HERMES_CODER_ROUTER_TOKEN_FILE",
                "/opt/data/.hermes-ops-client-token",
            )
        )
        self.timeout_seconds = max(3, int(timeout_seconds))

    def _token(self) -> str:
        try:
            token = self.token_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise CoderApiError(
                f"Не удалось прочитать token-файл {self.token_file}: {error}"
            ) from error
        if len(token) < 24:
            raise CoderApiError(
                f"Token-файл {self.token_file} пуст или содержит слишком короткое значение."
            )
        return token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[:2000]
            raise CoderApiError(
                f"Coder router вернул HTTP {error.code}: {_redact_text(details)}"
            ) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CoderApiError(
                f"Coder router недоступен: {type(error).__name__}"
            ) from error
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CoderApiError("Coder router вернул повреждённый JSON.") from error
        if not isinstance(result, dict):
            raise CoderApiError("Coder router вернул неожиданный тип ответа.")
        return redact(result)

    def health(self, project: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/coders/{project}/capabilities")

    def submit(
        self,
        project: str,
        *,
        task_id: str,
        task: str,
        source: str,
        task_type: str,
        complexity: str,
        risk: str,
        mutation_policy: str,
        requested_tier: str,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/v1/coders/{project}/runs",
            {
                "task_id": task_id,
                "task": task,
                "source": source,
                "task_type": task_type,
                "complexity": complexity,
                "risk": risk,
                "mutation_policy": mutation_policy,
                "requested_tier": requested_tier,
            },
        )

    def status(self, project: str, run_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/coders/{project}/runs/{run_id}")

    def stop(self, project: str, run_id: str) -> dict[str, Any]:
        return self.request("POST", f"/v1/coders/{project}/runs/{run_id}/stop", {})

    def pull_request(self, project: str, number: int) -> dict[str, Any]:
        return self.request("GET", f"/v1/coders/{project}/pulls/{number}")


def _update_from_status(
    ledger: Ledger,
    record: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    status = str(payload.get("status", "unknown"))
    updated = {
        **record,
        "status": status,
        "updated_at": _utc_now(),
        "last_event": payload.get("last_event"),
    }
    for field in _ROUTING_FIELDS:
        if field in payload:
            updated[field] = payload.get(field)
    if status in TERMINAL_STATUSES:
        updated["finished_at"] = _utc_now()
        updated["output"] = payload.get("output") or payload.get("error")
        updated["structured_output"] = payload.get("structured_output")
        structured = payload.get("structured_output")
        if isinstance(structured, dict):
            updated["memory_candidates"] = structured.get("memory_candidates") or []
        updated["usage"] = payload.get("usage")
    ledger.upsert(updated)
    return {
        **payload,
        "task_id": updated["task_id"],
        "project": updated["project"],
    }


def _print(payload: Any) -> None:
    print(json.dumps(redact(payload), ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Tier-aware управление изолированными Hermes coder-задачами."
    )
    parser.add_argument(
        "--ledger",
        default=os.getenv(
            "HERMES_CODER_LEDGER", "/opt/data/orchestration/tasks.json"
        ),
    )
    parser.add_argument("--timeout", type=int, default=30)
    commands = parser.add_subparsers(dest="command", required=True)

    health = commands.add_parser("health")
    health.add_argument("project", choices=("velvet", "max", "all"))

    submit = commands.add_parser("submit")
    submit.add_argument("project", choices=("velvet", "max"))
    submit.add_argument("--task", required=True)
    submit.add_argument(
        "--source",
        choices=(
            "kael-delegated", "owner-request", "owner-direct", "incident", "maintenance"
        ),
        default="kael-delegated",
    )
    submit.add_argument("--task-type", choices=TASK_TYPES, required=True)
    submit.add_argument("--complexity", choices=COMPLEXITIES, required=True)
    submit.add_argument("--risk", choices=RISKS, required=True)
    submit.add_argument(
        "--mutation-policy", choices=MUTATION_POLICIES, required=True
    )
    submit.add_argument(
        "--tier", dest="requested_tier", choices=TIERS, required=True
    )

    status = commands.add_parser("status")
    status.add_argument("reference")

    wait = commands.add_parser("wait")
    wait.add_argument("reference")
    wait.add_argument("--interval", type=float, default=5.0)
    wait.add_argument("--wait-timeout", type=int, default=3600)

    stop = commands.add_parser("stop")
    stop.add_argument("reference")

    listing = commands.add_parser("list")
    listing.add_argument("--project", choices=("velvet", "max"))
    listing.add_argument("--limit", type=int, default=20)

    pull = commands.add_parser("pr")
    pull.add_argument("project", choices=("velvet", "max"))
    pull.add_argument("number", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ledger = Ledger(Path(args.ledger))
    client = RouterClient(timeout_seconds=args.timeout)
    try:
        if args.command == "health":
            projects = tuple(_PROJECTS) if args.project == "all" else (args.project,)
            _print({project: client.health(project) for project in projects})
            return 0

        if args.command == "pr":
            _print(client.pull_request(args.project, args.number))
            return 0

        if args.command == "submit":
            clean_task = _redact_text(args.task).strip()
            if not clean_task:
                raise CoderApiError("Текст задачи пуст.")
            if len(clean_task) > 24_000:
                raise CoderApiError("Текст задачи превышает 24000 символов.")
            task_id = uuid.uuid4().hex
            routing = {
                "task_type": args.task_type,
                "complexity": args.complexity,
                "risk": args.risk,
                "mutation_policy": args.mutation_policy,
                "requested_tier": args.requested_tier,
            }
            response = client.submit(
                args.project,
                task_id=task_id,
                task=clean_task,
                source=_redact_text(args.source)[:128],
                **routing,
            )
            run_id = response.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise CoderApiError(f"Coder router не вернул run_id: {response!r}")
            repository, bot_handle = _PROJECTS[args.project]
            now = _utc_now()
            record = {
                "task_id": task_id,
                "project": args.project,
                "repository": repository,
                "coder": bot_handle,
                "run_id": run_id,
                "source": _redact_text(args.source)[:128],
                "task": clean_task,
                **routing,
                "selected_primary_model": response.get("selected_primary_model"),
                "selected_provider_route": response.get("selected_provider_route"),
                "attempted_models": response.get("attempted_models") or [],
                "attempted_routes": response.get("attempted_routes") or [],
                "actual_route": response.get("actual_route"),
                "fallback_reason": response.get("fallback_reason"),
                "mutation_started": bool(response.get("mutation_started")),
                "status": str(response.get("status", "started")),
                "created_at": now,
                "updated_at": now,
            }
            ledger.upsert(record)
            _print({**response, **record})
            return 0

        if args.command == "list":
            records = ledger.list()
            if args.project:
                records = [
                    item for item in records if item.get("project") == args.project
                ]
            _print(records[: max(1, args.limit)])
            return 0

        record = ledger.find(args.reference)
        if record is None:
            raise CoderApiError(
                f"Задача или run не найдены в журнале: {args.reference}"
            )
        project = str(record["project"])
        run_id = str(record["run_id"])

        if args.command == "status":
            payload = _update_from_status(
                ledger, record, client.status(project, run_id)
            )
            _print(payload)
            return 2 if str(payload.get("status")) in {"failed", "cancelled"} else 0

        if args.command == "stop":
            payload = client.stop(project, run_id)
            ledger.upsert(
                {**record, "status": "stopping", "updated_at": _utc_now()}
            )
            _print({**payload, "task_id": record["task_id"], "project": project})
            return 0

        if args.command == "wait":
            deadline = time.monotonic() + max(1, args.wait_timeout)
            while True:
                payload = _update_from_status(
                    ledger, record, client.status(project, run_id)
                )
                status_value = str(payload.get("status", "unknown"))
                if status_value in TERMINAL_STATUSES:
                    _print(payload)
                    return 0 if status_value == "completed" else 2
                if time.monotonic() >= deadline:
                    raise CoderApiError(
                        f"Ожидание run {run_id} превысило {args.wait_timeout} секунд."
                    )
                time.sleep(max(0.5, args.interval))
                refreshed = ledger.find(str(record["task_id"]))
                if refreshed is not None:
                    record = refreshed

        raise CoderApiError(f"Неизвестная команда: {args.command}")
    except CoderApiError as error:
        print(
            json.dumps(
                {"ok": False, "error": _redact_text(str(error))},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
