#!/usr/bin/env python3
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from codex_runner import (
    CodexManager,
    Handler,
    RunnerError,
    ThreadingHTTPServer,
)

_MODEL_DIRECTIVE = re.compile(
    r"(?i)(?:^|\s)(?:/model|model|модель)\s*[:=]?\s*"
    r"(luna|terra|sol|луна|терра|сол)\b"
)
_TIER_DIRECTIVE = re.compile(
    r"(?i)(?:^|\s)(?:/tier|tier|уровень)\s*[:=]?\s*"
    r"(small|standard|complex|high[_-]?risk)\b"
)
_TASK_TYPE_DIRECTIVE = re.compile(
    r"(?i)(?:^|\s)(?:/task[_-]?type|task[_-]?type|тип)\s*[:=]?\s*"
    r"(read[_-]?only|docs?|code|architecture|security|migration|incident)\b"
)
_RISK_DIRECTIVE = re.compile(
    r"(?i)(?:^|\s)(?:/risk|risk|риск)\s*[:=]?\s*"
    r"(low|medium|high|critical)\b"
)
_MUTATION_DIRECTIVE = re.compile(
    r"(?i)(?:^|\s)(?:/mutation|mutation|изменения)\s*[:=]?\s*"
    r"(read[_-]?only|workspace[_-]?pr)\b"
)
_HIGH_RISK = re.compile(
    r"(?i)(security|безопасност|секрет|credential|auth|авторизац|"
    r"миграц|schema change|race.?condition|гонк|payment|плат[её]ж|"
    r"critical incident|критическ.{0,20}инцидент|data loss|потер[яи].{0,20}данн)"
)
_ARCHITECTURE = re.compile(
    r"(?i)(архитектур|рефактор|несколько сервис|cross.?service|distributed|"
    r"multi.?service|system design|перепроектир)"
)
_INCIDENT = re.compile(r"(?i)(incident|инцидент|авари|outage|падени)")
_DOCS = re.compile(r"(?i)(readme|документац|docs?\b|инструкц|runbook|worklog)")
_READ_ONLY = re.compile(
    r"(?i)(read.?only|только чтени|проанализир|проверь статус|посмотри лог|"
    r"сводк|отч[её]т|диагностик|классифиц)"
)
_SMALL_CODE = re.compile(
    r"(?i)(опечатк|переимен|форматир|один тест|single test|"
    r"маленьк.{0,20}правк|прост.{0,20}правк|точечн.{0,20}правк|"
    r"одна строк|one.?line|lint|typing fix)"
)

_ALIASES = {
    "luna": "gpt-5.6-luna",
    "луна": "gpt-5.6-luna",
    "terra": "gpt-5.6-terra",
    "терра": "gpt-5.6-terra",
    "sol": "gpt-5.6-sol",
    "сол": "gpt-5.6-sol",
}
_MODEL_BY_TIER = {
    "small": "gpt-5.6-luna",
    "standard": "gpt-5.6-terra",
    "complex": "gpt-5.6-sol",
    "high_risk": "gpt-5.6-sol",
}
_TIERS_BY_MODEL = {
    "gpt-5.6-luna": frozenset({"small"}),
    "gpt-5.6-terra": frozenset({"standard"}),
    "gpt-5.6-sol": frozenset({"complex", "high_risk"}),
}
_TIER_RANK = {"small": 0, "standard": 1, "complex": 2, "high_risk": 3}
_TASK_TYPES = frozenset(
    {"read_only", "docs", "code", "architecture", "security", "migration", "incident"}
)
_TIERS = frozenset(_TIER_RANK)
_RISKS = frozenset({"low", "medium", "high", "critical"})
_MUTATION_POLICIES = frozenset({"read_only", "workspace_pr"})


@dataclass(frozen=True, slots=True)
class TaskClassification:
    task_type: str
    requested_tier: str
    risk: str
    mutation_policy: str
    model: str


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold().replace("-", "_")
    if normalized == "doc":
        normalized = "docs"
    return normalized or None


def _match(pattern: re.Pattern[str], prompt: str) -> str | None:
    match = pattern.search(prompt)
    return _normalize(match.group(1)) if match else None


def _validate(value: str | None, allowed: frozenset[str], field: str) -> str | None:
    normalized = _normalize(value)
    if normalized is not None and normalized not in allowed:
        raise ValueError(f"Некорректный {field}: {value}")
    return normalized


def _minimum_tier(task_type: str, risk: str) -> str:
    by_risk = {
        "low": "small",
        "medium": "standard",
        "high": "complex",
        "critical": "high_risk",
    }[risk]
    by_type = {
        "read_only": "small",
        "docs": "small",
        "code": "small",
        "architecture": "complex",
        "incident": "complex",
        "security": "high_risk",
        "migration": "high_risk",
    }[task_type]
    return max((by_risk, by_type), key=_TIER_RANK.__getitem__)


def classify_task(
    prompt: str,
    *,
    default: str,
    allowed: tuple[str, ...],
    model: str | None = None,
    task_type: str | None = None,
    requested_tier: str | None = None,
    risk: str | None = None,
    mutation_policy: str | None = None,
) -> TaskClassification:
    """Return one deterministic, non-downgrading routing decision.

    Explicit structured fields have priority. Prompt directives are only a
    compatibility path for direct/manual clients. The orchestrator should pass
    task_type, requested_tier, risk and mutation_policy explicitly.
    """

    clean = prompt.strip()
    model_directive = _MODEL_DIRECTIVE.search(clean)
    explicit_model = model
    if explicit_model is None and model_directive:
        explicit_model = _ALIASES[model_directive.group(1).casefold()]
    if explicit_model is not None and explicit_model not in allowed:
        raise ValueError("Запрошена неподдерживаемая Codex model")

    type_directive = _match(_TASK_TYPE_DIRECTIVE, clean)
    tier_directive = _match(_TIER_DIRECTIVE, clean)
    risk_directive = _match(_RISK_DIRECTIVE, clean)
    mutation_directive = _match(_MUTATION_DIRECTIVE, clean)
    small_code = bool(_SMALL_CODE.search(clean))

    resolved_type = _validate(task_type or type_directive, _TASK_TYPES, "task_type")
    if resolved_type is None:
        if _HIGH_RISK.search(clean):
            if re.search(r"(?i)(миграц|schema change)", clean):
                resolved_type = "migration"
            else:
                resolved_type = "security"
        elif _ARCHITECTURE.search(clean):
            resolved_type = "architecture"
        elif _INCIDENT.search(clean):
            resolved_type = "incident"
        elif _DOCS.search(clean):
            resolved_type = "docs"
        elif _READ_ONLY.search(clean):
            resolved_type = "read_only"
        else:
            resolved_type = "code"

    resolved_risk = _validate(risk or risk_directive, _RISKS, "risk")
    if resolved_risk is None:
        if resolved_type in {"security", "migration"}:
            resolved_risk = "critical"
        elif resolved_type in {"architecture", "incident"}:
            resolved_risk = "high"
        elif resolved_type in {"read_only", "docs"} or (
            resolved_type == "code" and small_code
        ):
            resolved_risk = "low"
        else:
            resolved_risk = "medium"

    tier_was_explicit = requested_tier is not None or tier_directive is not None
    resolved_tier = _validate(
        requested_tier or tier_directive, _TIERS, "requested_tier"
    )
    if resolved_tier is None:
        resolved_tier = _minimum_tier(resolved_type, resolved_risk)

    minimum_tier = _minimum_tier(resolved_type, resolved_risk)
    if _TIER_RANK[resolved_tier] < _TIER_RANK[minimum_tier]:
        raise ValueError(
            f"requested_tier {resolved_tier} ниже минимального {minimum_tier} "
            f"для task_type={resolved_type}, risk={resolved_risk}"
        )

    if explicit_model is not None:
        if tier_was_explicit and resolved_tier not in _TIERS_BY_MODEL[explicit_model]:
            raise ValueError("model не соответствует requested_tier")
        if not tier_was_explicit:
            model_tiers = _TIERS_BY_MODEL[explicit_model]
            if minimum_tier == "high_risk" and "high_risk" in model_tiers:
                resolved_tier = "high_risk"
            elif minimum_tier == "complex" and "complex" in model_tiers:
                resolved_tier = "complex"
            elif minimum_tier in model_tiers:
                resolved_tier = minimum_tier
            else:
                raise ValueError("model ниже минимального tier задачи")
        selected_model = explicit_model
    else:
        selected_model = _MODEL_BY_TIER[resolved_tier]

    if selected_model not in allowed:
        raise ValueError(
            f"Для requested_tier={resolved_tier} обязательная Codex model недоступна"
        )

    resolved_mutation = _validate(
        mutation_policy or mutation_directive,
        _MUTATION_POLICIES,
        "mutation_policy",
    )
    if resolved_mutation is None:
        resolved_mutation = "read_only" if resolved_type == "read_only" else "workspace_pr"
    if resolved_type == "read_only" and resolved_mutation != "read_only":
        raise ValueError("read_only task_type требует mutation_policy=read_only")

    return TaskClassification(
        task_type=resolved_type,
        requested_tier=resolved_tier,
        risk=resolved_risk,
        mutation_policy=resolved_mutation,
        model=selected_model,
    )


def select_model(prompt: str, *, default: str, allowed: tuple[str, ...]) -> str:
    return classify_task(prompt, default=default, allowed=allowed).model


class RoutedCodexManager(CodexManager):
    def capabilities(self) -> dict[str, Any]:
        payload = super().capabilities()
        return {
            **payload,
            "routing": {
                "default": self.default_model,
                "small": "gpt-5.6-luna",
                "standard": "gpt-5.6-terra",
                "complex": "gpt-5.6-sol",
                "high_risk": "gpt-5.6-sol",
                "explicit": ["luna", "terra", "sol"],
                "live_production_mutation": False,
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
        if not isinstance(prompt, str):
            return super().submit(payload)
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
        base_payload = {
            key: value
            for key, value in payload.items()
            if key in {"input", "session_id", "instructions"}
        }
        base_payload["model"] = classification.model
        record = super().submit(base_payload)
        run_id = str(record["run_id"])
        return self.store.update(
            run_id,
            task_type=classification.task_type,
            requested_tier=classification.requested_tier,
            risk=classification.risk,
            mutation_policy=classification.mutation_policy,
            selected_primary_model=classification.model,
            live_production_mutation=False,
        )


def main() -> int:
    host = os.environ.get("CODEX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("CODEX_RUNNER_PORT", "8642"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("CODEX_RUNNER_PORT должен быть от 1024 до 65535")
    manager = RoutedCodexManager()
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet routed Codex runner listening on {host}:{port}; "
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
