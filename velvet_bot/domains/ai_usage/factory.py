from __future__ import annotations

from velvet_bot.core.ai_budget import load_ai_budget_policy
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage.ledger import AIUsageRepository
from velvet_bot.domains.ai_usage.service import BudgetWarningHandler, AIUsageService
from velvet_bot.domains.ai_usage.task_service import AITaskQueueService
from velvet_bot.domains.ai_usage.tasks import AITaskRepository
from velvet_bot.infrastructure.postgres.ai_task_wakeup_repository import PostgresAITaskNotifier


def build_ai_usage_service(
    *,
    database: Database,
    warning_handler: BudgetWarningHandler | None = None,
    budget_timezone: str = "Europe/Warsaw",
) -> AIUsageService:
    return AIUsageService(
        AIUsageRepository(database),
        load_ai_budget_policy(),
        budget_timezone=budget_timezone,
        warning_handler=warning_handler,
    )


def build_ai_task_queue_service(*, database: Database) -> AITaskQueueService:
    return AITaskQueueService(
        AITaskRepository(database),
        notifier=PostgresAITaskNotifier(database),
    )


__all__ = (
    "build_ai_task_queue_service",
    "build_ai_usage_service",
)
