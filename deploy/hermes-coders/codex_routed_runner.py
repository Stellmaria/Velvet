#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from http import HTTPStatus
from typing import Any

from codex_runner import (
    CodexManager,
    Handler,
    RunnerError,
    ThreadingHTTPServer,
    utc_now,
)

TIERS = ("small", "standard", "complex", "high_risk")
TASK_TYPES = ("general", "code", "read_only", "documentation", "incident")
COMPLEXITIES = ("small", "standard", "complex")
RISKS = ("low", "medium", "high", "critical")
MUTATION_POLICIES = ("read_only", "workspace_write", "isolated_pr_only")

_TIER_RANK = {name: index for index, name in enumerate(TIERS)}
_MODEL_RANK = {
    "gpt-5.6-luna": 0,
    "gpt-5.6-terra": 1,
    "gpt-5.6-sol": 2,
}
_PRIMARY_BY_TIER = {
    "small": "gpt-5.6-luna",
    "standard": "gpt-5.6-terra",
    "complex": "gpt-5.6-sol",
    "high_risk": "gpt-5.6-sol",
}

_MODEL_DIRECTIVE = re.compile(
    r"(?im)(?:^|\n)\s*(?:/model|model|модель)\s*[:=]?\s*"
    r"(luna|terra|sol|луна|терра|сол)\b"
)
_TIER_DIRECTIVE = re.compile(
    r"(?im)(?:^|\n)\s*(?:/tier|tier|уровень)\s*[:=]?\s*"
    r"(small|standard|complex|high[_ -]?risk)\b"
)
_CODE_TASK = re.compile(
    r"(?i)(код|coder|code|bug|баг|исправ|реализ|функц|тест|pytest|diff|pr\b|"
    r"commit|ветк|repository|репозитор|callback|endpoint|api\b)"
)
_READ_ONLY_TASK = re.compile(
    r"(?i)(read.?only|только чтение|статус|сводк|классифиц|проанализируй|"
    r"проверь без измен|inspect|summary|status)"
)
_DOCUMENTATION_TASK = re.compile(
    r"(?i)(readme|документац|документ|runbook|worklog|описан|markdown|docs?\b)"
)
_COMPLEX_SCOPE = re.compile(
    r"(?i)(архитектур|рефактор|миграц|несколько сервис|cross.?service|"
    r"distributed|race.?condition|схем[аы] данных|совместимост|security|"
    r"безопасност|supply.?chain|production|продакш|rollback|депло)"
)
_BOUNDED_SCOPE = re.compile(
    r"(?i)(опечатк|переимен|форматир|маленьк|прост|bounded|один файл|"
    r"один тест|single test|typo)"
)
_HIGH_RISK = re.compile(
    r"(?i)(production|продакш|deploy|депло|restart|rollback|systemd|docker socket|"
    r"секрет|credential|auth|security|безопасност|миграц|удален.*данн|"
    r"payment|платеж|cross.?service)"
)
_ALIASES = {
    "luna": "gpt-5.6-luna",
    "луна": "gpt-5.6-luna",
    "terra": "gpt-5.6-terra",
    "терра": "gpt-5.6-terra",
    "sol": "gpt-5.6-sol",
    "сол": "gpt-5.6-sol",
}


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    task_type: str
    complexity: str
    risk: str
    mutation_policy: str
    requested_tier: str
    selected_primary_model: str
    selected_provider_route: str
    review_required: bool
    degraded_provider_route: bool


def _choice(name: str, value: Any, allowed: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RunnerError(HTTPStatus.BAD_REQUEST, f"{name} должен быть строкой")
    normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
    if normalized not in allowed:
        raise RunnerError(
            HTTPStatus.BAD_REQUEST,
            f"Некорректный {name}; допустимо: {', '.join(allowed)}",
        )
    return normalized


def infer_task_type(prompt: str) -> str:
    if _READ_ONLY_TASK.search(prompt):
        return "read_only"
    if _DOCUMENTATION_TASK.search(prompt) and not _CODE_TASK.search(prompt):
        return "documentation"
    if _CODE_TASK.search(prompt):
        return "code"
    return "general"


def infer_complexity(prompt: str, task_type: str) -> str:
    scope_hits = len(_COMPLEX_SCOPE.findall(prompt))
    if scope_hits >= 2 or (scope_hits and task_type in {"code", "incident"}):
        return "complex"
    if task_type in {"read_only", "documentation", "general"} and _BOUNDED_SCOPE.search(prompt):
        return "small"
    if task_type == "documentation" and len(prompt) <= 6_000:
        return "small"
    return "standard"


def infer_mutation_policy(task_type: str, complexity: str) -> str:
    if task_type in {"read_only", "general"}:
        return "read_only"
    if complexity == "complex" or task_type == "incident":
        return "isolated_pr_only"
    return "workspace_write"


def infer_risk(
    prompt: str,
    task_type: str,
    complexity: str,
    mutation_policy: str,
) -> str:
    if _HIGH_RISK.search(prompt):
        return "high"
    if complexity == "complex" or task_type == "incident":
        return "high"
    if mutation_policy == "read_only":
        return "low"
    return "medium"


def minimum_tier(complexity: str, risk: str) -> str:
    if risk in {"high", "critical"}:
        return "high_risk"
    if complexity == "complex":
        return "complex"
    if complexity == "small":
        return "small"
    return "standard"


def provider_route_for(requested_tier: str, task_type: str) -> tuple[str, ...]:
    if requested_tier == "small" and task_type == "code":
        return ("gpt-5.4-mini", "gpt-5.6-terra")
    if requested_tier == "small":
        return ("gpt-5.6-luna", "gpt-5.6-terra")
    return ("gpt-5.6-terra",)


def provider_route_name(requested_tier: str, task_type: str) -> str:
    models = provider_route_for(requested_tier, task_type)
    suffix = ">".join(models)
    if requested_tier in {"complex", "high_risk"}:
        return f"byesu_provider:{suffix}:degraded_review_required"
    return f"byesu_provider:{suffix}"


def primary_model_order(selected: str, requested_tier: str) -> tuple[str, ...]:
    """Return infrastructure-only upgrade order without any model downgrade."""

    if requested_tier in {"complex", "high_risk"}:
        preferred = ("gpt-5.6-sol",)
    elif requested_tier == "standard":
        preferred = ("gpt-5.6-terra", "gpt-5.6-sol")
    else:
        preferred = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
    if selected not in preferred:
        preferred = (selected, *preferred)
    result: list[str] = []
    selected_rank = _MODEL_RANK[selected]
    for model in preferred:
        if model not in result and _MODEL_RANK[model] >= selected_rank:
            result.append(model)
    return tuple(result)


def route_task(
    prompt: str,
    *,
    task_type: Any = None,
    complexity: Any = None,
    risk: Any = None,
    mutation_policy: Any = None,
    requested_tier: Any = None,
    explicit_model: Any = None,
    allowed_models: tuple[str, ...],
) -> RoutingDecision:
    clean_prompt = prompt.strip()
    resolved_task_type = _choice("task_type", task_type, TASK_TYPES) or infer_task_type(clean_prompt)
    resolved_complexity = (
        _choice("complexity", complexity, COMPLEXITIES)
        or infer_complexity(clean_prompt, resolved_task_type)
    )
    resolved_mutation = (
        _choice("mutation_policy", mutation_policy, MUTATION_POLICIES)
        or infer_mutation_policy(resolved_task_type, resolved_complexity)
    )
    resolved_risk = (
        _choice("risk", risk, RISKS)
        or infer_risk(
            clean_prompt,
            resolved_task_type,
            resolved_complexity,
            resolved_mutation,
        )
    )

    directive = _TIER_DIRECTIVE.search(clean_prompt)
    directive_tier = (
        directive.group(1).casefold().replace("-", "_").replace(" ", "_")
        if directive
        else None
    )
    explicit_tier = _choice("requested_tier", requested_tier, TIERS)
    if explicit_tier and directive_tier and explicit_tier != directive_tier:
        raise RunnerError(HTTPStatus.BAD_REQUEST, "Конфликт explicit tier и /tier directive")
    resolved_tier = explicit_tier or directive_tier or minimum_tier(
        resolved_complexity, resolved_risk
    )
    required = minimum_tier(resolved_complexity, resolved_risk)
    if _TIER_RANK[resolved_tier] < _TIER_RANK[required]:
        raise RunnerError(
            HTTPStatus.BAD_REQUEST,
            f"Tier {resolved_tier} ниже минимального {required} для указанного риска/сложности",
        )

    if resolved_tier in {"complex", "high_risk"}:
        if mutation_policy is not None and resolved_mutation != "isolated_pr_only":
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "complex/high_risk требует mutation_policy=isolated_pr_only",
            )
        resolved_mutation = "isolated_pr_only"

    model_directive = _MODEL_DIRECTIVE.search(clean_prompt)
    directive_model = _ALIASES[model_directive.group(1).casefold()] if model_directive else None
    requested_model: str | None = None
    if explicit_model is not None:
        if not isinstance(explicit_model, str):
            raise RunnerError(HTTPStatus.BAD_REQUEST, "model должен быть строкой")
        requested_model = explicit_model.strip()
        if requested_model not in allowed_models:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Запрошена неподдерживаемая Codex model")
    if requested_model and directive_model and requested_model != directive_model:
        raise RunnerError(HTTPStatus.BAD_REQUEST, "Конфликт explicit model и /model directive")
    selected_model = requested_model or directive_model or _PRIMARY_BY_TIER[resolved_tier]
    if selected_model not in allowed_models:
        raise RunnerError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            f"Primary model для tier {resolved_tier} недоступна в CODEX_ALLOWED_MODELS",
        )
    minimum_model = _PRIMARY_BY_TIER[resolved_tier]
    if _MODEL_RANK[selected_model] < _MODEL_RANK[minimum_model]:
        raise RunnerError(
            HTTPStatus.BAD_REQUEST,
            f"Model {selected_model} ниже требуемой {minimum_model} для tier {resolved_tier}",
        )

    review_required = resolved_tier in {"complex", "high_risk"}
    return RoutingDecision(
        task_type=resolved_task_type,
        complexity=resolved_complexity,
        risk=resolved_risk,
        mutation_policy=resolved_mutation,
        requested_tier=resolved_tier,
        selected_primary_model=selected_model,
        selected_provider_route=provider_route_name(resolved_tier, resolved_task_type),
        review_required=review_required,
        degraded_provider_route=review_required,
    )


def select_model(prompt: str, *, default: str, allowed: tuple[str, ...]) -> str:
    """Compatibility helper used by existing tests and bounded callers."""

    try:
        return route_task(prompt, allowed_models=allowed).selected_primary_model
    except RunnerError:
        return default


class RoutedCodexManager(CodexManager):
    def capabilities(self) -> dict[str, Any]:
        payload = super().capabilities()
        return {
            **payload,
            "routing": {
                "default": self.default_model,
                "tiers": list(TIERS),
                "task_types": list(TASK_TYPES),
                "explicit_models": ["luna", "terra", "sol"],
                "routes_by_tier": {
                    "small": {
                        "primary_model": "gpt-5.6-luna",
                        "provider_general": list(provider_route_for("small", "general")),
                        "provider_code": list(provider_route_for("small", "code")),
                        "minimum_mutation_policy": "read_only",
                    },
                    "standard": {
                        "primary_model": "gpt-5.6-terra",
                        "provider": list(provider_route_for("standard", "code")),
                        "minimum_mutation_policy": "workspace_write",
                    },
                    "complex": {
                        "primary_model": "gpt-5.6-sol",
                        "provider": list(provider_route_for("complex", "code")),
                        "degraded_provider_route": True,
                        "review_required": True,
                        "mutation_policy": "isolated_pr_only",
                    },
                    "high_risk": {
                        "primary_model": "gpt-5.6-sol",
                        "provider": list(provider_route_for("high_risk", "code")),
                        "degraded_provider_route": True,
                        "review_required": True,
                        "mutation_policy": "isolated_pr_only",
                    },
                },
                "downgrade_allowed": False,
            },
        }

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {
            "input",
            "session_id",
            "instructions",
            "model",
            "task_type",
            "complexity",
            "risk",
            "mutation_policy",
            "requested_tier",
            "tier",
        }
        if not set(payload).issubset(allowed_fields) or "input" not in payload:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Некорректный tier-aware Runs API payload")
        if "tier" in payload and "requested_tier" in payload:
            left = str(payload.get("tier") or "").strip().replace("-", "_")
            right = str(payload.get("requested_tier") or "").strip().replace("-", "_")
            if left != right:
                raise RunnerError(HTTPStatus.BAD_REQUEST, "tier и requested_tier конфликтуют")

        prompt = payload.get("input")
        instructions = payload.get("instructions", "")
        session_id = payload.get("session_id")
        if not isinstance(prompt, str) or not prompt.strip():
            raise RunnerError(HTTPStatus.BAD_REQUEST, "input должен быть непустой строкой")
        if len(prompt) > 30_000:
            raise RunnerError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "input превышает 30000 символов")
        if not isinstance(instructions, str) or len(instructions) > 8_000:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "instructions имеет неверный формат")
        if session_id is not None and (
            not isinstance(session_id, str) or len(session_id) > 200
        ):
            raise RunnerError(HTTPStatus.BAD_REQUEST, "session_id имеет неверный формат")
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

        decision = route_task(
            prompt,
            task_type=payload.get("task_type"),
            complexity=payload.get("complexity"),
            risk=payload.get("risk"),
            mutation_policy=payload.get("mutation_policy"),
            requested_tier=payload.get("requested_tier", payload.get("tier")),
            explicit_model=payload.get("model"),
            allowed_models=self.allowed_models,
        )
        run_id = uuid.uuid4().hex
        now = utc_now()
        record = {
            "run_id": run_id,
            "session_id": session_id,
            "status": "queued",
            "model": decision.selected_primary_model,
            **asdict(decision),
            "attempted_models": [],
            "attempted_routes": [],
            "actual_route": None,
            "fallback_reason": None,
            "mutation_started": False,
            "created_at": now,
            "updated_at": now,
            "last_event": {
                "type": "queued",
                "model": decision.selected_primary_model,
                "requested_tier": decision.requested_tier,
            },
        }
        self.store.write(record)
        thread = threading.Thread(
            target=self._execute,
            args=(
                run_id,
                prompt.strip(),
                instructions.strip(),
                decision.selected_primary_model,
            ),
            name=f"codex-run-{run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return record


def main() -> int:
    host = os.environ.get("CODEX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("CODEX_RUNNER_PORT", "8642"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("CODEX_RUNNER_PORT должен быть от 1024 до 65535")
    manager = RoutedCodexManager()
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet tier-aware Codex runner listening on {host}:{port}; "
        f"default={manager.default_model}; models={','.join(manager.allowed_models)}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
