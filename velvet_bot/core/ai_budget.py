from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_UP
from enum import StrEnum
from typing import Mapping

_MONEY_QUANTUM = Decimal("0.01")


class AIBudgetScope(StrEnum):
    VISION = "vision"
    ROLEPLAY = "roleplay"
    HERMES = "hermes"
    CODEX = "codex"


@dataclass(frozen=True, slots=True)
class AIBudgetPolicy:
    enabled: bool
    daily_limit_rub: Decimal
    monthly_limit_rub: Decimal
    max_request_rub: Decimal
    hermes_reserve_rub: Decimal
    warning_percents: tuple[int, ...] = (70, 85, 95)

    def __post_init__(self) -> None:
        for name, value in (
            ("daily_limit_rub", self.daily_limit_rub),
            ("monthly_limit_rub", self.monthly_limit_rub),
            ("max_request_rub", self.max_request_rub),
            ("hermes_reserve_rub", self.hermes_reserve_rub),
        ):
            if value < 0:
                raise ValueError(f"{name} не может быть отрицательным.")
        if self.enabled:
            if self.daily_limit_rub <= 0:
                raise ValueError("daily_limit_rub должен быть больше нуля.")
            if self.monthly_limit_rub <= 0:
                raise ValueError("monthly_limit_rub должен быть больше нуля.")
            if self.max_request_rub <= 0:
                raise ValueError("max_request_rub должен быть больше нуля.")
        if self.hermes_reserve_rub > self.monthly_limit_rub:
            raise ValueError("Резерв Hermes не может превышать месячный лимит.")
        if tuple(sorted(set(self.warning_percents))) != self.warning_percents:
            raise ValueError("warning_percents должны быть уникальными и отсортированными.")
        if any(percent <= 0 or percent >= 100 for percent in self.warning_percents):
            raise ValueError("warning_percents должны быть от 1 до 99.")


@dataclass(frozen=True, slots=True)
class AIUsageSnapshot:
    today_rub: Decimal = Decimal("0")
    month_rub: Decimal = Decimal("0")
    by_scope_month_rub: Mapping[AIBudgetScope, Decimal] | None = None

    def __post_init__(self) -> None:
        if self.today_rub < 0 or self.month_rub < 0:
            raise ValueError("Накопленный расход не может быть отрицательным.")


@dataclass(frozen=True, slots=True)
class AIBudgetDecision:
    allowed: bool
    reason: str
    estimated_cost_rub: Decimal
    daily_remaining_rub: Decimal
    monthly_remaining_rub: Decimal
    warning_percent: int | None = None


class AIBudgetGuard:
    def __init__(self, policy: AIBudgetPolicy) -> None:
        self.policy = policy

    def evaluate(
        self,
        *,
        scope: AIBudgetScope,
        estimated_cost_rub: Decimal,
        usage: AIUsageSnapshot,
    ) -> AIBudgetDecision:
        estimated = _money(estimated_cost_rub)
        if estimated < 0:
            raise ValueError("Оценочная стоимость запроса не может быть отрицательной.")

        daily_remaining = _money(self.policy.daily_limit_rub - usage.today_rub)
        monthly_cap = self._monthly_cap_for(scope)
        monthly_remaining = _money(monthly_cap - usage.month_rub)

        if not self.policy.enabled:
            return AIBudgetDecision(
                allowed=True,
                reason="Бюджетный guard выключен.",
                estimated_cost_rub=estimated,
                daily_remaining_rub=daily_remaining,
                monthly_remaining_rub=monthly_remaining,
            )

        if estimated > self.policy.max_request_rub:
            return self._deny(
                reason="Оценочная стоимость одного запроса превышает лимит.",
                estimated=estimated,
                daily_remaining=daily_remaining,
                monthly_remaining=monthly_remaining,
            )
        if usage.today_rub + estimated > self.policy.daily_limit_rub:
            return self._deny(
                reason="Дневной AI-бюджет исчерпан.",
                estimated=estimated,
                daily_remaining=daily_remaining,
                monthly_remaining=monthly_remaining,
            )
        if usage.month_rub + estimated > monthly_cap:
            if scope is AIBudgetScope.HERMES:
                reason = "Месячный AI-бюджет исчерпан, включая аварийный резерв Hermes."
            else:
                reason = "Месячный AI-бюджет исчерпан; резерв Hermes сохранён."
            return self._deny(
                reason=reason,
                estimated=estimated,
                daily_remaining=daily_remaining,
                monthly_remaining=monthly_remaining,
            )

        projected_month = usage.month_rub + estimated
        warning = self._warning_percent(projected_month)
        reason = "Запрос разрешён."
        if warning is not None:
            reason = f"Запрос разрешён; месячный бюджет достигнет {warning}% или больше."
        return AIBudgetDecision(
            allowed=True,
            reason=reason,
            estimated_cost_rub=estimated,
            daily_remaining_rub=_money(daily_remaining - estimated),
            monthly_remaining_rub=_money(monthly_remaining - estimated),
            warning_percent=warning,
        )

    def _monthly_cap_for(self, scope: AIBudgetScope) -> Decimal:
        if scope is AIBudgetScope.HERMES:
            return self.policy.monthly_limit_rub
        return self.policy.monthly_limit_rub - self.policy.hermes_reserve_rub

    def _warning_percent(self, projected_month: Decimal) -> int | None:
        if self.policy.monthly_limit_rub <= 0:
            return None
        ratio = projected_month * Decimal(100) / self.policy.monthly_limit_rub
        reached = [percent for percent in self.policy.warning_percents if ratio >= percent]
        return max(reached, default=None)

    @staticmethod
    def _deny(
        *,
        reason: str,
        estimated: Decimal,
        daily_remaining: Decimal,
        monthly_remaining: Decimal,
    ) -> AIBudgetDecision:
        return AIBudgetDecision(
            allowed=False,
            reason=reason,
            estimated_cost_rub=estimated,
            daily_remaining_rub=max(Decimal("0"), daily_remaining),
            monthly_remaining_rub=max(Decimal("0"), monthly_remaining),
        )


def load_ai_budget_policy() -> AIBudgetPolicy:
    enabled = _parse_bool(os.getenv("AI_BUDGET_ENABLED", "true"), "AI_BUDGET_ENABLED")
    warning_percents = _parse_warning_percents(
        os.getenv("AI_BUDGET_WARNING_PERCENTS", "70,85,95")
    )
    return AIBudgetPolicy(
        enabled=enabled,
        daily_limit_rub=_parse_money(
            os.getenv("AI_DAILY_BUDGET_RUB", "500"), "AI_DAILY_BUDGET_RUB"
        ),
        monthly_limit_rub=_parse_money(
            os.getenv("AI_MONTHLY_BUDGET_RUB", "5000"), "AI_MONTHLY_BUDGET_RUB"
        ),
        max_request_rub=_parse_money(
            os.getenv("AI_MAX_REQUEST_RUB", "250"), "AI_MAX_REQUEST_RUB"
        ),
        hermes_reserve_rub=_parse_money(
            os.getenv("AI_HERMES_RESERVE_RUB", "300"), "AI_HERMES_RESERVE_RUB"
        ),
        warning_percents=warning_percents,
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_UP)


def _parse_money(value: str, variable_name: str) -> Decimal:
    cleaned = value.strip().replace(",", ".")
    try:
        result = Decimal(cleaned)
    except InvalidOperation as error:
        raise RuntimeError(f"{variable_name} должен содержать сумму в рублях.") from error
    if not result.is_finite() or result < 0:
        raise RuntimeError(f"{variable_name} должен быть неотрицательной конечной суммой.")
    return _money(result)


def _parse_bool(value: str, variable_name: str) -> bool:
    cleaned = value.strip().casefold()
    if cleaned in {"1", "true", "yes", "on", "да"}:
        return True
    if cleaned in {"0", "false", "no", "off", "нет", ""}:
        return False
    raise RuntimeError(f"{variable_name} должен быть true/false.")


def _parse_warning_percents(value: str) -> tuple[int, ...]:
    result: set[int] = set()
    for item in value.split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        try:
            percent = int(cleaned)
        except ValueError as error:
            raise RuntimeError(
                "AI_BUDGET_WARNING_PERCENTS должен содержать проценты через запятую."
            ) from error
        if percent <= 0 or percent >= 100:
            raise RuntimeError("Порог предупреждения должен быть от 1 до 99.")
        result.add(percent)
    if not result:
        raise RuntimeError("AI_BUDGET_WARNING_PERCENTS не может быть пустым.")
    return tuple(sorted(result))


__all__ = (
    "AIBudgetDecision",
    "AIBudgetGuard",
    "AIBudgetPolicy",
    "AIBudgetScope",
    "AIUsageSnapshot",
    "load_ai_budget_policy",
)
