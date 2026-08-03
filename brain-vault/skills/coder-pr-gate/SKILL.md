---
name: coder-pr-gate
description: Классифицировать tier, передать задачу изолированному кодеру и проверить его PR по gateway evidence до любого merge или update.
version: 1.1.0
author: Velvet
---

# Coder PR gate

1. Выбери ровно `velvet` либо `max`; не создавай cross-project задачу.
2. До submit явно зафиксируй `task_type`, `requested_tier`, `risk`, `mutation_policy`.
3. Не занижай tier: medium требует минимум standard, high минимум complex, critical только high_risk; architecture/incident минимум complex; security/migration high_risk.
4. Удали secrets, персональные данные и нерелевантные логи из handoff.
5. Вызови `coderctl.py submit` со всеми routing flags, сохрани task/run IDs и дождись terminal state.
6. Проверь в run ledger `selected_primary_model`, `selected_primary_route`, `selected_provider_route`, `attempted_routes`, `actual_route`, `fallback_reason`, `degraded_execution`, `review_required`.
7. Из structured result возьми branch/PR/tests, но считай их заявлением агента.
8. Вызови `coderctl.py pr PROJECT NUMBER` и проверь head SHA, draft, mergeability, завершённость и успех checks.
9. Для complex/high_risk или degraded route дополнительно проверь scope diff, migration/rollback plan, security checks и отсутствие live-production privileges.
10. Сообщи владельцу evidence и blocker. Ни одна модель не выполняет merge, production update, restart или rollback без отдельного разрешения владельца.
