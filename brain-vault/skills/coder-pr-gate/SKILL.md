---
name: coder-pr-gate
description: Передать tier-aware задачу изолированному кодеру и проверить его PR по gateway evidence до любого merge или update.
version: 2.0.0
author: Velvet
---

# Coder PR gate

1. Выбери ровно `velvet` либо `max`; не создавай cross-project задачу.
2. Удали secrets, персональные данные и нерелевантные логи из handoff.
3. До submit отдельно зафиксируй `task_type`, `complexity`, `risk`,
   `mutation_policy` и `requested_tier`. Не классифицируй риск только длиной
   prompt и не понижай tier из-за недоступности модели.
4. Вызови `coderctl.py submit` только с полным явным контрактом:

   ```bash
   python /opt/data/tools/coderctl.py submit PROJECT \
     --source owner-request \
     --task-type TASK_TYPE \
     --complexity COMPLEXITY \
     --risk RISK \
     --mutation-policy MUTATION_POLICY \
     --tier REQUESTED_TIER \
     --task "TASK"
   ```

5. Сохрани task/run IDs и дождись terminal state. Проверь в ledger
   `requested_tier`, `selected_primary_model`, `selected_provider_route`,
   `attempted_models`, `attempted_routes`, `actual_route`, `fallback_reason` и
   `mutation_started`.
6. Из structured result возьми branch/PR/tests, но считай их заявлением агента.
7. Вызови `coderctl.py pr PROJECT NUMBER` и проверь head SHA, draft,
   mergeability, завершённость и успех checks.
8. Для `complex` или `high_risk` требуй `mutation_policy=isolated_pr_only` и
   независимый review. Degraded Terra route не получает production privileges.
9. Сообщи владельцу evidence и blocker. Не выполняй merge или production update
   без отдельного разрешения.
