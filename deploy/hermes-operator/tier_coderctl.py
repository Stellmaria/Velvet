#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

try:
    from coderctl_base import (  # type: ignore[import-not-found]
        CoderApiError,
        Ledger,
        RouterClient,
        TERMINAL_STATUSES,
        _PROJECTS,
        _print,
        _redact_text,
        _utc_now,
        redact,
    )
except ImportError:
    from coderctl import (
        CoderApiError,
        Ledger,
        RouterClient,
        TERMINAL_STATUSES,
        _PROJECTS,
        _print,
        _redact_text,
        _utc_now,
        redact,
    )

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


class TierRouterClient(RouterClient):
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


def update_from_status(
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
        choices=("owner-request", "incident", "maintenance"),
        default="owner-request",
    )
    submit.add_argument("--task-type", choices=TASK_TYPES, required=True)
    submit.add_argument("--complexity", choices=COMPLEXITIES, required=True)
    submit.add_argument("--risk", choices=RISKS, required=True)
    submit.add_argument(
        "--mutation-policy", choices=MUTATION_POLICIES, required=True
    )
    submit.add_argument("--tier", dest="requested_tier", choices=TIERS, required=True)

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
    client = TierRouterClient(timeout_seconds=args.timeout)
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
            payload = update_from_status(
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
                payload = update_from_status(
                    ledger, record, client.status(project, run_id)
                )
                status = str(payload.get("status", "unknown"))
                if status in TERMINAL_STATUSES:
                    _print(payload)
                    return 0 if status == "completed" else 2
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
